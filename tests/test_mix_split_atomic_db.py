# cspell:words lastrowid sscc
# cspell:words pytestmark
"""Two writers cannot create more stock than the locked mother contains."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import get_db_connection
from app.services.magazyn_dostawy.pallet_split_service import PalletSplitService
from app.services.magazyn_dostawy.pallet_mix_service import PalletMixService

pytestmark = pytest.mark.require_db


@pytest.fixture
def mother_stock(monkeypatch):
    token = 'TEST-SPLIT-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SHOW COLUMNS FROM magazyn_surowce')
    columns = {row[0] for row in cursor.fetchall()}
    for column, definition in {'linia': 'VARCHAR(20)', 'data_produkcji': 'DATE',
                              'data_przydatnosci': 'DATE', 'typ_opakowania': 'VARCHAR(50)'}.items():
        if column not in columns:
            cursor.execute(f'ALTER TABLE magazyn_surowce ADD COLUMN {column} {definition}')
    cursor.execute('''CREATE TABLE IF NOT EXISTS magazyn_agro_ruch (
        id INT AUTO_INCREMENT PRIMARY KEY,surowiec_id INT,surowiec_nazwa VARCHAR(255),
        typ_ruchu VARCHAR(100),ilosc DOUBLE,ilosc_po DOUBLE,lokalizacja VARCHAR(100),
        status VARCHAR(50),autor_login VARCHAR(100),autor_data DATETIME,komentarz TEXT) ENGINE=InnoDB''')
    cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja,linia) "
                   "VALUES(%s,%s,100,'MS01','AGRO')", (token,token))
    pallet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    # Simulate a cached advisory lookup. Every writer must re-read under its
    # own database lock, regardless of this deliberately stale snapshot.
    advisory = dict(id=pallet_id,nr_palety=token,nazwa=token,produkt=token,
                    stan_magazynowy=100,waga=100,source='surowiec',linia='AGRO',lokalizacja='MS01')
    monkeypatch.setattr(PalletSplitService,'find_by_sscc',lambda code: dict(advisory))
    yield token,pallet_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id,nr_palety FROM magazyn_surowce WHERE nazwa=%s',(token,))
    rows = cursor.fetchall()
    for row_id, code in rows:
        cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s OR paleta_id=%s',(code,row_id))
        cursor.execute('DELETE FROM magazyn_agro_ruch WHERE surowiec_id=%s',(row_id,))
    cursor.execute('DELETE FROM lab_blokady WHERE pallet_code=%s',(token,))
    cursor.execute('DELETE FROM magazyn_surowce WHERE nazwa=%s',(token,))
    conn.commit()
    conn.close()


@pytest.mark.parametrize('operation',['split','mix'])
def test_concurrent_consumption_keeps_total_weight(mother_stock,operation):
    token,_ = mother_stock
    def execute(_):
        try:
            if operation == 'split':
                return PalletSplitService.split_pallet(mother_sscc=token,weight_to_take=60)[0]
            return PalletMixService.mix_pallets([dict(nr_palety=token,weight_to_take=60)],token)[0]
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(execute,range(2))) == [False,True]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT stan_magazynowy FROM magazyn_surowce WHERE nazwa=%s',(token,))
    quantities = [float(row[0]) for row in cursor.fetchall()]
    conn.close()
    assert sorted(quantities) == [40,60]
    assert sum(quantities) == 100


@pytest.mark.parametrize('operation',['split','mix'])
def test_lab_hold_blocks_stock_mutation(mother_stock,operation):
    token,pallet_id = mother_stock
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO lab_blokady(pallet_id,pallet_code,status) VALUES(%s,%s,'BLOKADA_LAB')",(pallet_id,token))
    conn.commit()
    conn.close()
    with pytest.raises(ValueError,match='LAB'):
        if operation == 'split':
            PalletSplitService.split_pallet(mother_sscc=token,weight_to_take=60)
        else:
            PalletMixService.mix_pallets([dict(nr_palety=token,weight_to_take=60)],token)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(stan_magazynowy),COUNT(*) FROM magazyn_surowce WHERE nazwa=%s',(token,))
    assert cursor.fetchone() == (100,1)
    conn.close()
