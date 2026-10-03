"""Real database rollback and canonical pallet validation for external dispatches."""
import uuid
from unittest.mock import MagicMock, patch
import pytest
from app.db import get_db_connection
from app.repositories.warehouse_dispatch_repository import WarehouseDispatchRepository
from app.services.warehouse_dispatch_service import WarehouseDispatchService


@pytest.fixture
def stock_entries():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS magazyn_agro_surowce (
        id INT AUTO_INCREMENT PRIMARY KEY, nazwa VARCHAR(255), stan_magazynowy DECIMAL(12,3),
        nr_palety VARCHAR(100), nr_partii VARCHAR(100), lokalizacja VARCHAR(100)
        ) ENGINE=InnoDB''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS lab_blokady (
        id INT AUTO_INCREMENT PRIMARY KEY, pallet_code VARCHAR(100), status VARCHAR(50),
        INDEX idx_pallet_code (pallet_code)) ENGINE=InnoDB''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS magazyn_wyjazdy_samochodowe (
        id INT AUTO_INCREMENT PRIMARY KEY, nr_palety VARCHAR(100), nazwa_produktu VARCHAR(255),
        typ_palety VARCHAR(50), ilosc_kg DECIMAL(12,3), nr_rejestracyjny VARCHAR(100),
        kierowca VARCHAR(255), odbiorca VARCHAR(255), nr_dokumentu_wz VARCHAR(100), uwagi TEXT,
        magazynier VARCHAR(100), linia VARCHAR(50), created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS magazyn_ruchy_unified (
        id INT AUTO_INCREMENT PRIMARY KEY, movement_type VARCHAR(20), pallet_id INT, pallet_code VARCHAR(100),
        product_name VARCHAR(255), batch_number VARCHAR(100), source_location VARCHAR(100),
        target_location VARCHAR(100), quantity DECIMAL(12,3), unit VARCHAR(20), user_login VARCHAR(100),
        reference_id VARCHAR(100), notes TEXT, created_at DATETIME) ENGINE=InnoDB''')
    entries = []
    for index in range(2):
        code = 'TEST-WZ-' + uuid.uuid4().hex.upper()
        cursor.execute('INSERT INTO magazyn_agro_surowce (nazwa,stan_magazynowy,nr_palety,nr_partii,lokalizacja) VALUES (%s,100,%s,%s,%s)',
                       ('Test', code, 'TEST', 'MS01'))
        entries.append({'pallet_id': cursor.lastrowid, 'src_table': 'magazyn_agro_surowce',
                        'nr_palety': code, 'nazwa_produktu': 'Test', 'typ_palety': 'Surowiec',
                        'linia': 'AGRO', 'ilosc_kg': 100, 'batch': 'TEST', 'required_batch': 'TEST',
                        'magazynier': 'pytest'})
    conn.commit()
    conn.close()
    yield entries
    conn = get_db_connection()
    cursor = conn.cursor()
    for entry in entries:
        cursor.execute('DELETE FROM magazyn_ruchy_unified WHERE pallet_code=%s', (entry['nr_palety'],))
        cursor.execute('DELETE FROM magazyn_wyjazdy_samochodowe WHERE nr_palety=%s', (entry['nr_palety'],))
        cursor.execute('DELETE FROM magazyn_agro_surowce WHERE id=%s', (entry['pallet_id'],))
    conn.commit()
    conn.close()


def assert_stock_and_documents(entries, stock, count):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for entry in entries:
            cursor.execute('SELECT stan_magazynowy FROM magazyn_agro_surowce WHERE id=%s', (entry['pallet_id'],))
            assert float(cursor.fetchone()[0]) == stock
            for table, column in [('magazyn_wyjazdy_samochodowe', 'nr_palety'), ('magazyn_ruchy_unified', 'pallet_code')]:
                cursor.execute(f'SELECT COUNT(*) FROM {table} WHERE {column}=%s', (entry['nr_palety'],))
                assert cursor.fetchone()[0] == count
    finally:
        conn.close()


@pytest.mark.require_db
def test_batch_commits_stock_documents_and_ledger_together(stock_entries):
    assert len(WarehouseDispatchRepository().dispatch_batch(stock_entries)) == 2
    assert_stock_and_documents(stock_entries, 0, 1)


@pytest.mark.require_db
def test_second_pallet_failure_rolls_back_first_stock_change(stock_entries):
    stock_entries[1]['ilosc_kg'] = 101
    with pytest.raises(ValueError):
        WarehouseDispatchRepository().dispatch_batch(stock_entries)
    assert_stock_and_documents(stock_entries, 100, 0)


@pytest.mark.require_db
def test_ledger_failure_rolls_back_stock_and_dispatch_document(stock_entries):
    with patch('app.repositories.warehouse_movement_ledger_repository.WarehouseMovementLedgerRepository.record_movement', side_effect=RuntimeError('Test')):
        with pytest.raises(RuntimeError):
            WarehouseDispatchRepository().dispatch_batch(stock_entries)
    assert_stock_and_documents(stock_entries, 100, 0)


@pytest.mark.parametrize('batch', [False, True])
def test_lab_hold_blocks_single_and_batch_dispatch(batch):
    repo = MagicMock()
    repo.find_pallet_by_code.return_value = {'id': 1, 'nr_palety': 'TEST', 'nazwa': 'Test',
                                            'typ': 'Surowiec', 'linia': 'AGRO',
                                            'stan_magazynowy': 100, 'src_table': 'magazyn_agro_surowce'}
    item = {'nr_palety': 'TEST', 'ilosc_kg': 100, 'src_table': 'forged', 'linia': 'PSD'}
    with patch('app.services.lab_quality_service.LabQualityService.check_pallet_lab_status', return_value={'is_blocked': True}):
        assert WarehouseDispatchService(repo).dispatch_pallet_to_vehicle({'pallets': [item]} if batch else item, 'pytest')[0] is False
    repo.dispatch_batch.assert_not_called()


def test_client_source_and_product_are_replaced_by_database_values():
    repo = MagicMock()
    repo.find_pallet_by_code.return_value = {'id': 1, 'nr_palety': 'TEST', 'nazwa': 'Real',
                                            'typ': 'Surowiec', 'linia': 'AGRO',
                                            'stan_magazynowy': 100, 'src_table': 'magazyn_agro_surowce'}
    repo.dispatch_batch.return_value = [1]
    with patch('app.services.lab_quality_service.LabQualityService.check_pallet_lab_status', return_value={'is_blocked': False}):
        assert WarehouseDispatchService(repo).dispatch_pallet_to_vehicle({'nr_palety': 'TEST', 'ilosc_kg': 100, 'src_table': 'forged', 'nazwa_produktu': 'False'}, 'pytest')[0]
    entry = repo.dispatch_batch.call_args.args[0][0]
    assert entry['src_table'] == 'magazyn_agro_surowce'
    assert entry['nazwa_produktu'] == 'Real'
