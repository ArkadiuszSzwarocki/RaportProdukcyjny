# cspell:words BFMS lastrowid neighbour pytestmark sscc
"""Exercise concurrent live transfer writes against real MySQL."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import get_db_connection
from app.services.magazyn_dostawy.commands.live_transfer_service import LiveTransferService
from app.services.magazyn_dostawy.commands.delivery_cancellation_service import DeliveryCancellationService
from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor

pytestmark = pytest.mark.require_db


@pytest.fixture
def stock_document():
    token = 'TEST-LIVE-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    numbers = [token + '-1', token + '-2']
    for nr in numbers:
        cursor.execute(
            "INSERT INTO magazyn_surowce (nr_palety,nazwa,stan_magazynowy,lokalizacja) "
            "VALUES (%s,%s,100,'MS01')", (nr, token))
    cursor.execute(
        "INSERT INTO magazyn_dostawy (id,order_ref,status,items,linia) "
        "VALUES (%s,%s,'OCZEKUJE','[]','AGRO')", (token, token))
    conn.commit()
    conn.close()
    yield token, numbers
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM magazyn_dostawy WHERE id=%s", (token,))
    cursor.execute("DELETE FROM palety_historia WHERE nr_palety IN (%s,%s)", tuple(numbers))
    cursor.execute("DELETE FROM magazyn_surowce WHERE nr_palety IN (%s,%s)", tuple(numbers))
    conn.commit()
    conn.close()


def test_two_operators_do_not_overwrite_each_others_items(stock_document):
    doc, numbers = stock_document
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda nr: LiveTransferService.add_live_transfer_item(doc, {'nr_palety': nr}), numbers))
    assert all(result[0] for result in results), results
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT items FROM magazyn_dostawy WHERE id=%s", (doc,))
    items = json.loads(cursor.fetchone()['items'])
    conn.close()
    assert {item['nr_palety'] for item in items} == set(numbers)
    assert len({item['id'] for item in items}) == 2


def test_cancel_restores_only_requested_pallet_and_keeps_neighbour(stock_document):
    doc, numbers = stock_document
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_surowce SET lokalizacja='BFMS01' WHERE nr_palety IN (%s,%s)", tuple(numbers))
    cursor.execute("UPDATE magazyn_dostawy SET items=%s WHERE id=%s", (json.dumps([
        {'id': 'one', 'nr_palety': numbers[0], 'originalSpot': 'MS01', 'sourceSpot': 'BFMS01',
         'productName': doc}]), doc))
    conn.commit()
    conn.close()
    ok, message = DeliveryCancellationService.cancel_dostawa(doc)
    assert ok, message
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nr_palety,lokalizacja FROM magazyn_surowce WHERE nr_palety IN (%s,%s)", tuple(numbers))
    locations = dict(cursor.fetchall())
    conn.close()
    assert locations == {numbers[0]: 'MS01', numbers[1]: 'BFMS01'}


def test_agro_view_is_one_physical_pallet_not_ambiguous_duplicate(stock_document):
    doc, _ = stock_document
    code = doc + '-FG'
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("INSERT INTO magazyn_palety (nr_palety,produkt,waga_netto,linia,lokalizacja) "
                       "VALUES (%s,'Test',100,'AGRO','MGW01')", (code,))
        pallet_id = cursor.lastrowid
        conn.commit()
        PalletLockManager.set_pallets_blocked(cursor, [{'nr_palety': code}], 1)
        conn.commit()
        row, typ, table = InternalTransferProcessor._find_active_pallet_by_sscc(cursor, code, 'AGRO')
        assert row['id'] == pallet_id
        assert typ == 'wyrob_gotowy'
        cursor.execute(f"SELECT is_blocked FROM {table} WHERE id=%s", (pallet_id,))
        assert cursor.fetchone()['is_blocked'] == 1
    finally:
        conn.rollback()
        cursor.execute("DELETE FROM magazyn_palety WHERE nr_palety=%s", (code,))
        conn.commit()
        conn.close()


def test_opening_pending_view_never_moves_stock_or_same_id_neighbour(stock_document):
    from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries
    doc,numbers=stock_document
    conn=get_db_connection()
    cursor=conn.cursor()
    cursor.execute('SELECT id FROM magazyn_surowce WHERE nr_palety=%s',(numbers[0],))
    pallet_id=cursor.fetchone()[0]
    neighbour='TEST-NEIGHBOUR-'+uuid.uuid4().hex[:16]
    cursor.execute("INSERT INTO magazyn_palety(id,nr_palety,produkt,waga_netto,lokalizacja,linia,is_loaded) VALUES(%s,%s,'Neighbour',50,'MP01','PSD',1)",(pallet_id,neighbour))
    cursor.execute('UPDATE magazyn_dostawy SET items=%s WHERE id=%s',
                   (json.dumps([dict(id='ONE',sourcePalletId=pallet_id,nr_palety=numbers[0],sourceSpot='MS01')]),doc))
    conn.commit()
    try:
        DeliveryQueries.sync_pending_transfers_blocked_state()
        cursor.execute('SELECT lokalizacja,stan_magazynowy,is_blocked FROM magazyn_surowce WHERE nr_palety=%s',(numbers[0],))
        assert cursor.fetchone()==('MS01',100,1)
        cursor.execute('SELECT lokalizacja,waga_netto,is_blocked,is_loaded FROM magazyn_palety WHERE nr_palety=%s',(neighbour,))
        assert cursor.fetchone()==('MP01',50,0,1)
    finally:
        conn.rollback()
        cursor.execute('DELETE FROM magazyn_palety WHERE nr_palety=%s',(neighbour,))
        conn.commit()
        conn.close()


def test_transit_stock_cannot_enter_second_live_or_final_transfer(stock_document):
    """Both write paths retain the physical transit state and the empty document."""
    from app.services.magazyn_dostawy.commands.delivery_save_service import DeliverySaveService
    doc, numbers = stock_document
    code = numbers[0]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_surowce SET lokalizacja='W_TRANZYCIE_OSIP',is_blocked=1 WHERE nr_palety=%s",(code,))
    conn.commit()
    conn.close()
    item = dict(id='new',nr_palety=code,sourcePalletNo=code,sourceTable='magazyn_surowce',
                sourceSpot='MS01',productName=doc,netWeight=100)
    ok, message = LiveTransferService.add_live_transfer_item(doc,item,linia='AGRO')
    assert not ok and 'tranzycie' in message
    for skip in (False,True):
        ok, message = DeliverySaveService.save_dostawa(dict(id=doc,linia='AGRO',items=[dict(item)],skip_warehouse_lookup=skip))
        assert not ok and 'tranzycie' in message
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        PalletLockManager.set_pallets_blocked(cursor,[dict(nr_palety=code,sourceTable='magazyn_surowce')],0,exclude_delivery_id=doc)
        conn.commit()
        cursor.execute('SELECT items FROM magazyn_dostawy WHERE id=%s',(doc,))
        assert json.loads(cursor.fetchone()['items']) == []
        cursor.execute('SELECT lokalizacja,stan_magazynowy,is_blocked FROM magazyn_surowce WHERE nr_palety=%s',(code,))
        stock = cursor.fetchone()
        assert stock['lokalizacja']=='W_TRANZYCIE_OSIP'
        assert float(stock['stan_magazynowy'])==100
        assert stock['is_blocked']==1
        cursor.execute('SELECT lokalizacja,is_blocked FROM magazyn_surowce WHERE nr_palety=%s',(numbers[1],))
        neighbour = cursor.fetchone()
        assert neighbour['lokalizacja']=='MS01' and not neighbour['is_blocked']
    finally:
        conn.rollback()
        conn.close()
