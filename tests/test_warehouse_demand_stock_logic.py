from datetime import datetime
from unittest.mock import MagicMock, patch

from app.repositories.warehouse_order_repository import WarehouseOrderRepository


def test_searchable_locations_include_central_warehouse_and_exclude_forbidden_zones():
    allowed = [
        'R010101',
        'RR030602',
        '010102',
        'MP01',
        'BF_MP01',
        'MGW01',
        'MGW02',
        'MOP01',
        'MDM01',
        'PSD01',
    ]
    forbidden = [
        'OSIP',
        'W_TRANZYCIE_OSIP',
        'OS01',
        'MS01',
        'BFMS01',
        'BF_MS01',
        'BF-MS01',
        'BF MS01',
        'RAMPA',
        'LP01',
        'PRODUKCJA',
    ]

    for location in allowed:
        assert WarehouseOrderRepository._is_searchable_location(location) is True, location

    for location in forbidden:
        assert WarehouseOrderRepository._is_searchable_location(location) is False, location


def test_check_stock_uses_exact_material_match_and_skips_reserved_and_forbidden_locations():
    now = datetime(2026, 9, 30, 8, 0, 0)
    db_rows = [
        {'id': 1, 'nr_palety': 'P1', 'nazwa': 'Surowiec A', 'stan_magazynowy': 100.0, 'lokalizacja': 'R010101', 'nr_partii': 'L1', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 2, 'nr_palety': 'P2', 'nazwa': 'Surowiec A', 'stan_magazynowy': 200.0, 'lokalizacja': '010102', 'nr_partii': 'L2', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 3, 'nr_palety': 'P3', 'nazwa': 'Surowiec A', 'stan_magazynowy': 50.0, 'lokalizacja': 'MP01', 'nr_partii': 'L3', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 4, 'nr_palety': 'P4', 'nazwa': 'Surowiec A', 'stan_magazynowy': 75.0, 'lokalizacja': 'BF_MP01', 'nr_partii': 'L4', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 5, 'nr_palety': 'P5', 'nazwa': 'Surowiec A', 'stan_magazynowy': 500.0, 'lokalizacja': 'MS01', 'nr_partii': 'L5', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 6, 'nr_palety': 'P6', 'nazwa': 'Surowiec A', 'stan_magazynowy': 600.0, 'lokalizacja': 'BF_MS01', 'nr_partii': 'L6', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 7, 'nr_palety': 'P7', 'nazwa': 'Surowiec A', 'stan_magazynowy': 700.0, 'lokalizacja': 'OSIP', 'nr_partii': 'L7', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 8, 'nr_palety': 'P8', 'nazwa': 'Surowiec A', 'stan_magazynowy': 800.0, 'lokalizacja': 'RAMPA', 'nr_partii': 'L8', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 9, 'nr_palety': 'P9', 'nazwa': 'Surowiec A Plus', 'stan_magazynowy': 900.0, 'lokalizacja': 'R020101', 'nr_partii': 'L9', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
        {'id': 10, 'nr_palety': 'P10', 'nazwa': 'Surowiec A', 'stan_magazynowy': 30.0, 'lokalizacja': 'R020202', 'nr_partii': 'L10', 'fifo_date': now, 'created_at': now, 'is_blocked': 1, 'powod_blokady': 'JAKOŚĆ'},
        {'id': 99, 'nr_palety': 'P99', 'nazwa': 'Surowiec A', 'stan_magazynowy': 1000.0, 'lokalizacja': 'R030303', 'nr_partii': 'L99', 'fifo_date': now, 'created_at': now, 'is_blocked': 0, 'powod_blokady': ''},
    ]

    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [{'paleta_id': 99}],
        db_rows,
    ]
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch('app.repositories.warehouse_order_repository.get_db_connection', return_value=connection), \
         patch('app.repositories.warehouse_order_repository.get_table_name', return_value='magazyn_surowce'):
        result = WarehouseOrderRepository.check_stock(['Surowiec A'], 'AGRO')

    stock = result['stock_data']['Surowiec A']
    assert stock['stan_magazynowy_kg'] == 425.0
    assert stock['zablokowane_kg'] == 30.0
    assert set(stock['lokalizacje']) == {'R010101', '010102', 'MP01', 'BF_MP01'}
    assert stock['lokalizacje_zablokowane'] == ['R020202']

    ids = [p['id'] for p in stock['palety_fifo']]
    assert ids == [1, 2, 3, 4, 10]
    assert 99 not in ids
    assert 9 not in ids
    assert all(p['lokalizacja'] not in {'MS01', 'BF_MS01', 'OSIP', 'RAMPA'} for p in stock['palety_fifo'])

    active = [p for p in stock['palety_fifo'] if not p['is_blocked']]
    assert [p['fifo_rank'] for p in active] == [1, 2, 3, 4]
    assert stock['palety_fifo'][-1]['fifo_rank'] is None


def test_location_normalization_catches_all_bfms01_variants():
    assert WarehouseOrderRepository._norm_location('BF_MS01') == 'BFMS01'
    assert WarehouseOrderRepository._norm_location('BF-MS01') == 'BFMS01'
    assert WarehouseOrderRepository._norm_location('BF MS01') == 'BFMS01'
