# cspell:words lastrowid
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
    service.begin_receiving(transfer.id, 'pytest')
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
    if phase == 'receive':
        service.begin_receiving(transfer.id, 'pytest')
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
    service.begin_receiving(transfer.id, 'pytest')
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
    service.begin_receiving(transfer.id, 'pytest')
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
    service.begin_receiving(transfer.id, 'pytest')
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
    # This test injects an insert failure after validation; the fixture pallet is
    # already reserved, which is tested separately by the planning guards.
    monkeypatch.setattr(service, '_validate_planned_pallets', lambda *args: None)
    with pytest.raises(RuntimeError,match='Injected'):
        service.create_transfer_order('MS01','OSIP',[
            dict(nr_palety=code,product_name='Test',requested_qty=100,item_type='raw')],'pytest')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM osip_transfers')
    assert cursor.fetchone()[0] == before
    conn.close()


def test_receipt_requires_explicit_start(transfer_stock):
    service, transfer, code = transfer_stock
    service.dispatch_transfer(transfer.id, [], 'pytest')
    before = snapshot(transfer.id,code)
    with pytest.raises(ValueError,match='Odbierz'):
        service.receive_single_item(transfer.id,code,'OSIP','pytest')
    assert snapshot(transfer.id,code) == before
    assert service.begin_receiving(transfer.id,'pytest').status == 'RECEIVING'


def test_main_scanner_guard_requires_start_and_correct_destination(transfer_stock):
    service, transfer, code = transfer_stock
    service.dispatch_transfer(transfer.id, [], 'pytest')
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        with pytest.raises(ValueError,match='Odbierz'):
            service.require_receiving(cursor,code,'OSIP')
        conn.rollback()
        service.begin_receiving(transfer.id,'pytest')
        with pytest.raises(ValueError,match='docelowego'):
            service.require_receiving(cursor,code,'MS01')
        conn.rollback()
        assert service.require_receiving(cursor,code,'OSIP')
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize('source,destination,target', [('MS01', 'OSIP', 'A98'), ('OSIP', 'MS01', 'MS01')])
def test_scanned_transfer_api_edit_load_and_receive_complete_cycle(transfer_stock, monkeypatch, source, destination, target):
    from flask import Flask
    from app.blueprints.osip import osip_bp
    service, original, code = transfer_stock
    service.cancel_transfer(original.id, 'pytest')
    second_code = code + '-SECOND'
    location = 'A97' if source == 'OSIP' else 'MS01'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE magazyn_surowce SET lokalizacja=%s WHERE nr_palety=%s', (location, code))
    cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES(%s,'Second test pallet',200,%s)", (second_code, location))
    conn.commit()
    conn.close()
    app = Flask(__name__)
    app.secret_key = 'isolated-transfer-test'
    app.register_blueprint(osip_bp)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola='masteradmin')
    monkeypatch.setattr('app.core.production_permissions._page_allowed', lambda *args, **kwargs: True)
    created_id = None
    try:
        response = client.get('/osip/api/transfers/lookup-pallet', query_string={'source': source, 'code': code})
        assert response.status_code == 200, response.json
        first = response.json['pallet']
        assert first['requested_qty'] == 100
        created = client.post('/osip/api/transfers', json=dict(source_warehouse=source, destination_warehouse=destination, items=[first]))
        assert created.status_code == 200, created.json
        created_id = created.json['transfer_id']
        second_response = client.get('/osip/api/transfers/lookup-pallet', query_string={'source': source, 'code': second_code})
        assert second_response.status_code == 200, second_response.json
        second = second_response.json['pallet']
        assert client.put(f'/osip/api/transfers/{created_id}', json=dict(items=[first, second], notes='Added pallet')).json['success']
        assert len(service.get_transfer_by_id(created_id).items) == 2
        edited = client.put(f'/osip/api/transfers/{created_id}', json=dict(items=[second], notes='Final load'))
        assert edited.status_code == 200, edited.json
        transfer = service.get_transfer_by_id(created_id)
        assert transfer.notes == 'Final load'
        assert [item.nr_palety for item in transfer.items] == [second_code]
        assert snapshot(created_id, code)[0][0] == location
        # Wrong warehouse, unknown code and stale planning must not produce placeholder pallets.
        wrong_source = 'MS01' if source == 'OSIP' else 'OSIP'
        assert client.get('/osip/api/transfers/lookup-pallet', query_string={'source': wrong_source, 'code': second_code}).status_code == 400
        assert client.get('/osip/api/transfers/lookup-pallet', query_string={'source': source, 'code': code + '-UNKNOWN'}).status_code == 400
        dispatch = client.post(f'/osip/api/transfers/{created_id}/dispatch', json={'loaded_pallets': []})
        assert dispatch.status_code == 200, dispatch.json
        assert snapshot(created_id, second_code)[0] == ('W_TRANZYCIE_OSIP', 200)
        edit_after_load = client.put(f'/osip/api/transfers/{created_id}', json=dict(items=[first], notes='Forbidden'))
        assert edit_after_load.status_code == 400
        assert service.get_transfer_by_id(created_id).notes == 'Final load'
        assert client.post(f'/osip/api/transfers/{created_id}/begin_receive', json={}).json['success']
        receipt = client.post(f'/osip/api/transfers/{created_id}/scan_receive', json=dict(pallet_code=second_code, target_location=target))
        assert receipt.status_code == 200, receipt.json
        assert receipt.json['completed']
        assert snapshot(created_id, second_code)[0] == (target, 200)
        assert snapshot(created_id, second_code)[1:] == ('COMPLETED', ('RECEIVED', 200))
    finally:
        conn = get_db_connection()
        cursor = conn.cursor()
        if created_id:
            cursor.execute('DELETE FROM osip_transfers WHERE id=%s', (created_id,))
        for pallet_code in (code, second_code):
            cursor.execute('DELETE FROM magazyn_ruchy_unified WHERE pallet_code=%s', (pallet_code,))
            cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s', (pallet_code,))
        cursor.execute('DELETE FROM magazyn_surowce WHERE nr_palety=%s', (second_code,))
        conn.commit()
        conn.close()


def test_edit_failure_rolls_back_original_items_and_notes(transfer_stock, monkeypatch):
    service, transfer, code = transfer_stock
    before = service.get_transfer_by_id(transfer.id)
    def fail(*args, **kwargs):
        raise RuntimeError('Injected edit failure')
    monkeypatch.setattr(service.repository, 'add_transfer_items', fail)
    with pytest.raises(RuntimeError, match='Injected edit failure'):
        service.update_planned_transfer(transfer.id, [dict(pallet_id=before.items[0].pallet_id, nr_palety=code,
            requested_qty=100, item_type='raw')], 'Must roll back', 'pytest')
    after = service.get_transfer_by_id(transfer.id)
    assert [(item.id, item.nr_palety) for item in after.items] == [(item.id, item.nr_palety) for item in before.items]
    assert after.notes == before.notes


def test_duplicate_planned_transfer_and_duplicate_edit_pallet_are_rejected(transfer_stock):
    service, transfer, code = transfer_stock
    item = dict(pallet_id=transfer.items[0].pallet_id, nr_palety=code, requested_qty=100, item_type='raw')
    with pytest.raises(ValueError, match='innego aktywnego transferu'):
        service.create_transfer_order('MS01', 'OSIP', [item], 'pytest')
    with pytest.raises(ValueError, match='więcej niż raz'):
        service.update_planned_transfer(transfer.id, [item, item], None, 'pytest')
    assert len(service.get_transfer_by_id(transfer.id).items) == 1



def test_concurrent_plans_cannot_reserve_same_pallet(transfer_stock):
    service, original, code = transfer_stock
    service.cancel_transfer(original.id, 'pytest')
    item = dict(pallet_id=original.items[0].pallet_id, nr_palety=code, requested_qty=100, item_type='raw')
    def plan(_):
        try:
            return OsipTransferService().create_transfer_order('MS01', 'OSIP', [item], 'pytest').id
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(plan, range(2)))
    created = [result for result in results if result is not None]
    try:
        assert len(created) == 1
    finally:
        conn = get_db_connection()
        cursor = conn.cursor()
        for transfer_id in created:
            cursor.execute('DELETE FROM osip_transfers WHERE id=%s', (transfer_id,))
        conn.commit()
        conn.close()
