# cspell:words pytestmark
"""Real-MySQL failure injection for stock, item and document transactions."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import get_db_connection
from app.services.osip_transfer_service import OsipTransferService

pytestmark = pytest.mark.require_db


@pytest.fixture
def transfer_stock():
    token = 'TEST-OSIP-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja) "
                   "VALUES(%s,'Test',100,'MS01')", (token,))
    pallet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    service = OsipTransferService()
    transfer = service.create_transfer_order('MS01','OSIP',[
        dict(pallet_id=pallet_id,nr_palety=token,product_name='Test',requested_qty=100,item_type='raw')], 'pytest')
    yield service, transfer, token
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM osip_transfers WHERE id=%s', (transfer.id,))
    cursor.execute('DELETE FROM magazyn_ruchy_unified WHERE pallet_code=%s', (token,))
    cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s', (token,))
    cursor.execute('DELETE FROM magazyn_surowce WHERE nr_palety=%s', (token,))
    conn.commit()
    conn.close()


def snapshot(transfer_id, code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT lokalizacja,stan_magazynowy FROM magazyn_surowce WHERE nr_palety=%s', (code,))
    stock = cursor.fetchone()
    cursor.execute('SELECT status FROM osip_transfers WHERE id=%s', (transfer_id,))
    status = cursor.fetchone()[0]
    cursor.execute('SELECT status,loaded_qty FROM osip_transfer_items WHERE transfer_id=%s', (transfer_id,))
    item = cursor.fetchone()
    conn.close()
    return stock, status, item


def test_dispatch_and_receive_commit_all_three_states(transfer_stock):
    service, transfer, code = transfer_stock
    dispatched = service.dispatch_transfer(transfer.id, [], 'pytest')
    assert dispatched.status == 'IN_TRANSIT'
    stock, status, item = snapshot(transfer.id, code)
    assert stock == ('W_TRANZYCIE_OSIP', 100)
    assert (status, item[0], float(item[1])) == ('IN_TRANSIT','LOADED',100)
    result = service.receive_single_item(transfer.id, code, 'OSIP', 'pytest')
    assert result['completed']
    stock, status, item = snapshot(transfer.id, code)
    assert stock == ('OSIP', 100)
    assert (status, item[0]) == ('COMPLETED','RECEIVED')


@pytest.mark.parametrize('phase', ['dispatch', 'receive', 'cancel'])
def test_header_failure_rolls_back_stock_and_item(transfer_stock, monkeypatch, phase):
    service, transfer, code = transfer_stock
    if phase != 'dispatch':
        service.dispatch_transfer(transfer.id, [], 'pytest')
    before = snapshot(transfer.id, code)
    def fail(*args, **kwargs):
        raise RuntimeError('Injected header failure')
    monkeypatch.setattr(service.repository, 'update_transfer_status', fail)
    with pytest.raises(RuntimeError, match='Injected'):
        if phase == 'dispatch':
            service.dispatch_transfer(transfer.id, [], 'pytest')
        elif phase == 'receive':
            service.receive_single_item(transfer.id, code, 'OSIP', 'pytest')
        else:
            service.cancel_transfer(transfer.id, 'pytest')
    assert snapshot(transfer.id, code) == before


def test_partial_weight_does_not_move_entire_pallet(transfer_stock):
    service, transfer, code = transfer_stock
    item = transfer.items[0]
    with pytest.raises(ValueError, match='pełny stan'):
        service.dispatch_transfer(transfer.id,[dict(id=item.id, pallet_id=item.pallet_id,
            nr_palety=code,loaded_qty=20)],'pytest')
    assert snapshot(transfer.id,code)[0] == ('MS01',100)


def test_two_receipts_produce_one_state_transition(transfer_stock):
    service, transfer, code = transfer_stock
    service.dispatch_transfer(transfer.id, [], 'pytest')
    def receive(_):
        try:
            return OsipTransferService().receive_single_item(transfer.id,code,'OSIP','pytest')['success']
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(receive,range(2))) == [False,True]
    assert snapshot(transfer.id,code)[1:] == ('COMPLETED', ('RECEIVED',100))


def test_auto_receipt_uses_callers_transaction(transfer_stock):
    service, transfer, code = transfer_stock
    service.dispatch_transfer(transfer.id, [], 'pytest')
    before = snapshot(transfer.id, code)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_surowce SET lokalizacja='OSIP' WHERE nr_palety=%s", (code,))
    assert service.auto_receive_pallet_by_code(code,'OSIP','pytest',external_conn=conn)[0]
    conn.rollback()
    conn.close()
    assert snapshot(transfer.id, code) == before


def test_receipt_rejects_location_in_wrong_warehouse(transfer_stock):
    service, transfer, code = transfer_stock
    service.dispatch_transfer(transfer.id, [], 'pytest')
    before = snapshot(transfer.id, code)
    with pytest.raises(ValueError,match='docelowego'):
        service.receive_single_item(transfer.id,code,'MS01','pytest')
    assert snapshot(transfer.id, code) == before


def test_dispatch_rejects_pallet_from_wrong_source(transfer_stock):
    service, transfer, code = transfer_stock
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_surowce SET lokalizacja='OSIP' WHERE nr_palety=%s",(code,))
    conn.commit()
    conn.close()
    before = snapshot(transfer.id,code)
    with pytest.raises(ValueError,match='źródłowym'):
        service.dispatch_transfer(transfer.id,[],'pytest')
    assert snapshot(transfer.id,code) == before


def test_create_item_failure_does_not_leave_empty_header(transfer_stock, monkeypatch):
    service, _, code = transfer_stock
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM osip_transfers')
    before = cursor.fetchone()[0]
    conn.close()
    def fail(*args, **kwargs):
        raise RuntimeError('Injected item failure')
    monkeypatch.setattr(service.repository,'add_transfer_items',fail)
    with pytest.raises(RuntimeError,match='Injected'):
        service.create_transfer_order('MS01','OSIP',[
            dict(nr_palety=code,product_name='Test',requested_qty=100,item_type='raw')],'pytest')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM osip_transfers')
    assert cursor.fetchone()[0] == before
    conn.close()
