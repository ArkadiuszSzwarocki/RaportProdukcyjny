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
