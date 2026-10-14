# cspell:words pytestmark sscc lastrowid
"""Order positions are fulfilled once, only by canonical scanned stock."""
import json
import uuid

import pytest
from app.db import get_db_connection
from app.services.warehouse_order_fulfillment import WarehouseOrderFulfillment
from app.services.magazyn_dostawy.commands.live_transfer_service import LiveTransferService

pytestmark = pytest.mark.require_db


@pytest.fixture
def order_stock():
    token = 'TEST-ORDER-' + uuid.uuid4().hex.upper()
    conn = get_db_connection()
    cur = conn.cursor()
    for index, weight in enumerate((60,40)):
        cur.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES(%s,%s,%s,'MS01')",
                    (token+str(index),token,weight))
    cur.execute("INSERT INTO magazyn_zamowienia(items,operator_login) VALUES(%s,%s)",
                (json.dumps([dict(surowiec_nazwa=token,ilosc_kg=100,linia='AGRO')]),token))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    yield token,order_id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM magazyn_zamowienia WHERE operator_login=%s',(token,))
    cur.execute('DELETE FROM magazyn_dostawy WHERE created_by=%s',(token,))
    cur.execute('DELETE FROM palety_historia WHERE nr_palety IN (%s,%s)',(token+'0',token+'1'))
    cur.execute('DELETE FROM magazyn_surowce WHERE nazwa=%s',(token,))
    conn.commit()
    conn.close()


def state(order_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT status,items FROM magazyn_zamowienia WHERE id=%s',(order_id,))
    row = cur.fetchone()
    conn.close()
    items = json.loads(row['items'])
    return row['status'],sum(float(a['kg']) for item in items for a in item.get('transfer_allocations',[]))


def sync(token,items,line='AGRO',rollback=False):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        WarehouseOrderFulfillment.sync_transfer(cur,token,items,line,'pytest')
        conn.rollback() if rollback else conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_partial_and_complete_then_repeat_scan(order_stock):
    token,order_id = order_stock
    first = dict(id='first',nr_palety=token+'0',netWeight=60)
    second = dict(id='second',nr_palety=token+'1',netWeight=40)
    sync(token,[first])
    assert state(order_id) == ('NOWE',60)
    sync(token,[first,second])
    assert state(order_id) == ('ZAMKNIETE',100)
    sync(token,[first,second])
    assert state(order_id) == ('ZAMKNIETE',100)


def test_removal_reopens_order_and_cancel_revokes_quantity(order_stock):
    token,order_id = order_stock
    first,second = [dict(id=str(i),nr_palety=token+str(i)) for i in range(2)]
    sync(token,[first,second])
    sync(token,[first])
    assert state(order_id) == ('NOWE',60)
    sync(token,[])
    assert state(order_id) == ('NOWE',0)


def test_rollback_preserves_unfulfilled_order(order_stock):
    token,order_id = order_stock
    sync(token,[dict(id='a',nr_palety=token+'0')],rollback=True)
    assert state(order_id) == ('NOWE',0)


def test_wrong_hall_does_not_fulfill_order(order_stock):
    token,order_id = order_stock
    sync(token,[dict(id='a',nr_palety=token+'0')],line='PSD')
    assert state(order_id) == ('NOWE',0)


def test_client_cannot_inflate_weight(order_stock):
    token,order_id = order_stock
    with pytest.raises(ValueError,match='Ilość transferu'):
        sync(token,[dict(id='a',nr_palety=token+'0',netWeight=100)])
    assert state(order_id) == ('NOWE',0)


def test_same_sscc_in_another_document_is_not_counted_twice(order_stock):
    token,order_id = order_stock
    item = dict(id='a',nr_palety=token+'0')
    sync(token,[item])
    sync(token+'-OTHER',[item])
    assert state(order_id) == ('NOWE',60)


def test_one_pallet_does_not_close_other_material(order_stock):
    token,order_id = order_stock
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE magazyn_zamowienia SET items=%s WHERE id=%s',
                (json.dumps([dict(surowiec_nazwa=token,ilosc_kg=60),dict(surowiec_nazwa='other',ilosc_kg=100)]),order_id))
    conn.commit()
    conn.close()
    sync(token,[dict(id='a',nr_palety=token+'0',productName='other')])
    assert state(order_id) == ('NOWE',60)


def test_live_scan_and_remove_use_order_transaction(order_stock):
    token,order_id = order_stock
    ok,result = LiveTransferService.init_live_transfer(login=token)
    assert ok,result
    transfer_id = result['dostawa_id']
    ok,result = LiveTransferService.add_live_transfer_item(transfer_id,dict(nr_palety=token+'0'),login=token)
    assert ok,result
    assert state(order_id) == ('NOWE',60)
    assert LiveTransferService.remove_live_transfer_item(transfer_id,item_id=result['item_id'])[0]
    assert state(order_id) == ('NOWE',0)
