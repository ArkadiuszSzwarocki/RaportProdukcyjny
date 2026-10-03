# cspell:words lastrowid sscc
"""Releasing one reason must preserve other physical pallet holds."""
# cspell:words pytestmark
import json
import uuid

import pytest

from app.db import get_db_connection
from app.repositories.lab_quality_repository import LabQualityRepository
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.warehouse_v2.pallet_status_service import PalletStatusService

pytestmark = pytest.mark.require_db


@pytest.fixture
def reserved_stock():
    code = 'TEST-HOLD-' + uuid.uuid4().hex
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SHOW COLUMNS FROM magazyn_dostawy')
    columns = {row[0] for row in cur.fetchall()}
    for column, definition in {'potwierdzone_przez':'VARCHAR(100)', 'potwierdzone_at':'DATETIME'}.items():
        if column not in columns:
            cur.execute(f'ALTER TABLE magazyn_dostawy ADD COLUMN {column} {definition}')
    cur.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja,is_blocked) "
                "VALUES(%s,'Test',100,'MS01',1)", (code,))
    pallet_id = cur.lastrowid
    conn.commit()
    conn.close()
    yield code, pallet_id
    conn = get_db_connection()
    cur = conn.cursor()
    for table, column in [('magazyn_dostawy','order_ref'),('lab_blokady','pallet_code'),
                          ('palety_historia','nr_palety'),('magazyn_surowce','nr_palety')]:
        cur.execute(f'DELETE FROM {table} WHERE {column}=%s', (code,))
    conn.commit()
    conn.close()


def current_block(code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT is_blocked FROM magazyn_surowce WHERE nr_palety=%s', (code,))
    result = cur.fetchone()[0]
    conn.close()
    return result


@pytest.mark.parametrize('hold', ['lab','manual','other_document','none'])
def test_release_reservation_preserves_other_holds(reserved_stock, hold):
    code, pallet_id = reserved_stock
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if hold == 'lab':
        cur.execute("INSERT INTO lab_blokady(pallet_id,pallet_code,status) VALUES(%s,%s,'BLOKADA_LAB')", (pallet_id,code))
    elif hold == 'manual':
        cur.execute("INSERT INTO palety_historia(paleta_id,nr_palety,linia,akcja) VALUES(%s,%s,'AGRO','BLOKADA')", (pallet_id,code))
    elif hold == 'other_document':
        cur.execute("INSERT INTO magazyn_dostawy(id,order_ref,status,items,linia) VALUES(%s,%s,'OPEN',%s,'AGRO')",
                    (code,code,json.dumps([dict(nr_palety=code)])))
    PalletLockManager.set_pallets_blocked(cur,[dict(nr_palety=code,sourceTable='magazyn_surowce')],0)
    conn.commit()
    conn.close()
    assert current_block(code) == (0 if hold == 'none' else 1)


def test_lab_release_preserves_transfer_reservation(reserved_stock):
    code, pallet_id = reserved_stock
    LabQualityRepository.block_pallet_in_lab(pallet_id,code,'surowiec','AGRO','test','pytest')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO magazyn_dostawy(id,order_ref,status,items,linia) VALUES(%s,%s,'OPEN',%s,'AGRO')",
                (code,code,json.dumps([dict(nr_palety=code)])))
    conn.commit()
    conn.close()
    assert LabQualityRepository.release_pallet_from_lab(code,'surowiec','AGRO','pytest')
    assert current_block(code) == 1


def test_lab_wrong_identity_cannot_block_another_pallet(reserved_stock):
    code,pallet_id = reserved_stock
    with pytest.raises(ValueError,match='Nie znaleziono'):
        LabQualityRepository.block_pallet_in_lab(pallet_id,code+'-WRONG','surowiec','AGRO','test','pytest')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM lab_blokady WHERE pallet_id=%s',(pallet_id,))
    assert cur.fetchone()[0] == 0
    conn.close()


def test_manual_unlock_keeps_active_lab_hold(reserved_stock):
    code,pallet_id = reserved_stock
    LabQualityRepository.block_pallet_in_lab(pallet_id,code,'surowiec','AGRO','test','pytest')
    ok, message = PalletStatusService.toggle_block(pallet_id,'Surowiec','pytest',linia='AGRO',sscc=code)
    assert ok, message
    assert current_block(code) == 1


def test_document_confirmation_rolls_back_with_physical_move(reserved_stock):
    code,pallet_id = reserved_stock
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("INSERT INTO magazyn_dostawy(id,order_ref,status,items,linia) VALUES(%s,%s,'OCZEKUJE',%s,'AGRO')",
                (code,code,json.dumps([dict(nr_palety=code,sourceTable='magazyn_surowce')])))
    conn.commit()
    cur.execute("UPDATE magazyn_surowce SET lokalizacja='OSIP' WHERE id=%s", (pallet_id,))
    AcceptanceService.confirm_moved_pallet(cur,conn,code,'OSIP','pytest')
    conn.rollback()
    cur.execute('SELECT status,items FROM magazyn_dostawy WHERE id=%s',(code,))
    row = cur.fetchone()
    assert row['status'] == 'OCZEKUJE'
    assert not json.loads(row['items'])[0].get('accepted')
    cur.execute('SELECT lokalizacja,is_blocked FROM magazyn_surowce WHERE id=%s',(pallet_id,))
    assert cur.fetchone() == dict(lokalizacja='MS01',is_blocked=1)
    conn.close()


def test_auto_confirmation_rejects_multiple_pending_documents(reserved_stock):
    code,_ = reserved_stock
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        for suffix in ('-1','-2'):
            cur.execute("INSERT INTO magazyn_dostawy(id,order_ref,status,items,linia) VALUES(%s,%s,'OCZEKUJE',%s,'AGRO')",
                        (code+suffix,code,json.dumps([dict(nr_palety=code)])))
        conn.commit()
        with pytest.raises(ValueError,match='wielu pozycji'):
            AcceptanceService.confirm_moved_pallet(cur,conn,code,'OSIP','pytest')
        conn.rollback()
        cur.execute('SELECT status FROM magazyn_dostawy WHERE order_ref=%s',(code,))
        assert [row['status'] for row in cur.fetchall()] == ['OCZEKUJE','OCZEKUJE']
    finally:
        conn.close()
