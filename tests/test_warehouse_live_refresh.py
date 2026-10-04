# cspell:words pytestmark sscc lastrowid
"""Receiving counters and stale forms must agree with physical stock."""
import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.db import get_db_connection
from app.services.magazyn_dostawy.commands.internal_transfer_processor import InternalTransferProcessor


def test_archive_lookup_with_sscc_never_queries_foreign_id():
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    assert InternalTransferProcessor._is_pallet_archived_or_zero(cursor, 'CURRENT-SSCC', 734) == (False, '')
    assert cursor.execute.call_count == 1
    assert cursor.execute.call_args.args[1] == ('CURRENT-SSCC',)


def test_save_refusal_keeps_operator_message(client, monkeypatch):
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin')
    monkeypatch.setattr('app.services.magazyn_dostawy.delivery_command_service.DeliveryCommandService.save_dostawa',
                        lambda *args: (False, 'Paleta jest już w innym przesunięciu.'))
    response = client.post('/magazyn-dostawy/api/zapisz', json={'linia': 'AGRO', 'items': []})
    assert response.status_code == 400
    assert response.get_json()['message'] == 'Paleta jest już w innym przesunięciu.'


def test_stale_form_cannot_undo_a_receipt(monkeypatch):
    from app.services.magazyn_dostawy.commands import delivery_save_service as module
    old = dict(id='one', nr_palety='PHYSICAL', productName='Test', accepted=True, lokalizacja_przyjecia='MP01')
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = dict(status='OCZEKUJE', items=json.dumps([old]), supplier='', linia='AGRO')
    cursor.fetchall.return_value = [dict(nazwa='Test')]
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(module.DeliveryOrderValidator, 'validate', lambda *a: (True, ''))
    monkeypatch.setattr(module.PalletLockManager, 'set_pallets_blocked', lambda *a, **k: None)
    seen = []
    def process(cursor, items, *args):
        seen.extend(items)
        return True, items
    monkeypatch.setattr(module.InternalTransferProcessor, 'process_transfer', process)
    monkeypatch.setattr('app.services.warehouse_order_fulfillment.WarehouseOrderFulfillment.sync_transfer', lambda *a: None)
    stale = dict(old, accepted=False, lokalizacja_przyjecia=None)
    assert module.DeliverySaveService.save_dostawa(dict(id='doc', linia='AGRO', items=[stale]))[0]
    assert seen[0]['accepted']
    assert seen[0]['lokalizacja_przyjecia'] == 'MP01'


def test_distinct_sscc_with_same_local_id_are_not_deduplicated(monkeypatch):
    from app.services.magazyn_dostawy.commands import live_transfer_service as module
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = dict(id='doc', status='OCZEKUJE', items=json.dumps([
        dict(id='one', nr_palety='FIRST', sourcePalletId=734)]))
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(module.PalletLockManager, 'set_pallets_blocked', lambda *a, **k: None)
    monkeypatch.setattr('app.services.warehouse_order_fulfillment.WarehouseOrderFulfillment.sync_transfer', lambda *a: None)
    ok, result = module.LiveTransferService.add_live_transfer_item('doc', dict(nr_palety='SECOND', sourcePalletId=734))
    assert ok
    assert len(result['items']) == 2


@pytest.mark.require_db
def test_counter_excludes_accepted_live_items_and_empty_orders(app):
    from app.core.contexts import _fetch_delivery_counters
    before = _fetch_delivery_counters()['pending_transfer_pallets']['ALL']
    document_id = 'TEST-' + uuid.uuid4().hex[:12]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO magazyn_dostawy(id,status,linia,lokalizacja_z,items) VALUES(%s,'OCZEKUJE','AGRO','MS01',%s)",
                       (document_id, json.dumps([dict(accepted=True), dict(accepted=False)])))
        conn.commit()
        assert _fetch_delivery_counters()['pending_transfer_pallets']['ALL'] == before + 1
        cursor.execute('UPDATE magazyn_dostawy SET items=%s WHERE id=%s', (json.dumps([dict(accepted=True)]), document_id))
        conn.commit()
        assert _fetch_delivery_counters()['pending_transfer_pallets']['ALL'] == before
    finally:
        cursor.execute('DELETE FROM magazyn_dostawy WHERE id=%s', (document_id,))
        conn.commit()
        conn.close()


@pytest.mark.require_db
def test_osip_receipt_can_use_agro_instead_of_suggested_ms01(app):
    from app.services.osip_transfer_service import OsipTransferService
    code = 'TEST-OSIP-AGRO-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    transfer = None
    try:
        cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja,nr_partii,data_produkcji,data_przydatnosci) VALUES(%s,'Test',100,'OSIP','LOT-1','2026-01-01','2027-01-01')", (code,))
        pallet_id = cursor.lastrowid
        conn.commit()
        service = OsipTransferService()
        transfer = service.create_transfer_order('OSIP', 'MS01', [dict(pallet_id=pallet_id, nr_palety=code, product_name='Test', requested_qty=100)], 'pytest')
        service.dispatch_transfer(transfer.id, [], 'pytest')
        dates = service.pallet_metadata([service.get_transfer_by_id(transfer.id)])[('magazyn_surowce', code)]
        assert dates['nr_partii'] == 'LOT-1'
        assert str(dates['data_przydatnosci']) == '2027-01-01'
        service.begin_receiving(transfer.id, 'pytest')
        assert service.receive_single_item(transfer.id, code, 'MGW01', 'pytest')['success']
        cursor.execute('SELECT lokalizacja FROM magazyn_surowce WHERE nr_palety=%s', (code,))
        assert cursor.fetchone()[0] == 'MGW01'
    finally:
        if transfer:
            cursor.execute('DELETE FROM osip_transfers WHERE id=%s', (transfer.id,))
        cursor.execute('DELETE FROM magazyn_ruchy_unified WHERE pallet_code=%s', (code,))
        cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s', (code,))
        cursor.execute('DELETE FROM magazyn_surowce WHERE nr_palety=%s', (code,))
        conn.commit()
        conn.close()
