# cspell:words putaway sscc
# cspell:words pytestmark lastrowid
"""Database regressions for receiving phases, stock identity and concurrent racks."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from app.db import get_db_connection
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.magazyn_dostawy.commands.external_delivery_processor import ExternalDeliveryProcessor
from app.services.planning.start_guard import guard_section_start
from app.utils.location_validator import check_rack_location_availability

pytestmark = pytest.mark.require_db


def test_internal_receipt_rejects_wrong_explicit_destination(app, pending_delivery):
    destination = 'MS01'
    document_id, code, item = pending_delivery
    item['sourceSpot'] = 'OCZEKUJĄCE'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_dostawy SET supplier=NULL,lokalizacja_z='WIELE',lokalizacja_do=%s,items=%s WHERE id=%s", (destination, json.dumps([item]), document_id))
    conn.commit()
    conn.close()
    before = delivery_snapshot(document_id, code)
    result = AcceptanceService.accept_item(document_id, 'one', 'MP01', 'pytest')
    assert not result[0]
    assert 'przeznaczona do MS01' in result[1]
    assert delivery_snapshot(document_id, code) == before


def test_cancellation_does_not_restore_into_occupied_rack(pending_delivery):
    from app.services.magazyn_dostawy.commands.delivery_cancellation_service import DeliveryCancellationService
    _, code, item = pending_delivery
    occupied = 'TEST-OCCUPIED-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES(%s,'Test rack',100,'R880102')", (occupied,))
        item.update(sourceSpot='RAMPA', originalSpot='R880102')
        with pytest.raises(ValueError, match='zajęta'):
            DeliveryCancellationService.restore_buffered_items(cursor, [item], 'AGRO', 'TEST', 'pytest')
        cursor.execute('SELECT lokalizacja FROM magazyn_opakowania WHERE nr_palety=%s', (code,))
        assert cursor.fetchone()['lokalizacja'] == 'RAMPA'
    finally:
        conn.rollback()
        conn.close()


def test_live_movement_assigns_destination_during_receipt(app, pending_delivery):
    document_id, code, item = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_dostawy SET supplier=NULL,status='OCZEKUJE',lokalizacja_z='RAMPA',lokalizacja_do='',items=%s WHERE id=%s", (json.dumps([item]), document_id))
    conn.commit()
    conn.close()
    result = AcceptanceService.accept_item(document_id, 'one', 'MS01', 'pytest')
    assert result[0], result[1]
    assert delivery_snapshot(document_id, code)[2] == ('MS01', 100)
    assert delivery_snapshot(document_id, code)[0] == 'OCZEKUJE'
    from app.services.magazyn_dostawy.commands.live_transfer_service import LiveTransferService
    assert LiveTransferService.close_live_transfer(document_id, 'pytest')[0]
    assert delivery_snapshot(document_id, code)[0] == 'COMPLETED'


def test_history_quantity_uses_code_and_correct_warehouse(app):
    from app.services.warehouse_v2.pallet_history_service import PalletHistoryService
    codes = ['TEST-HISTORY-' + uuid.uuid4().hex for _ in range(2)]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT GREATEST(COALESCE((SELECT MAX(id) FROM magazyn_palety),0),COALESCE((SELECT MAX(id) FROM magazyn_palety_agro),0))+10')
        record_id = cursor.fetchone()[0]
        for offset, (code, quantity, hall) in enumerate(zip(codes, (1000, 150), ('PSD', 'AGRO'))):
            cursor.execute('INSERT INTO magazyn_palety(id,nr_palety,produkt,waga_netto,linia,lokalizacja) VALUES(%s,%s,%s,%s,%s,\'MS01\')',
                           (record_id + offset, code, 'Test history', quantity, hall))
        cursor.execute("INSERT INTO palety_historia(paleta_id,nr_palety,linia,typ_palety,akcja,komentarz) VALUES(%s,%s,'AGRO','wyrob_gotowy','PRZYJECIE',%s)", (record_id, codes[1], codes[1]))
        conn.commit()
        events = PalletHistoryService.get_pallet_history(record_id, 'Wyrób Gotowy', 'AGRO', sscc=codes[1])
        event = next(event for event in events if event.get('komentarz') == codes[1])
        assert event['quantity_after'] == 150
    finally:
        for table, code in zip(('magazyn_palety', 'magazyn_palety_agro'), codes):
            cursor.execute(f'DELETE FROM {table} WHERE nr_palety=%s', (code,))
        cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s', (codes[1],))
        conn.commit()
        conn.close()


@pytest.fixture
def pending_delivery():
    code = 'TEST-WMS-' + uuid.uuid4().hex
    document_id = uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO magazyn_opakowania (nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES (%s,'Test packaging',100,'RAMPA')", (code,))
    item = dict(id='one', sourcePalletId=cursor.lastrowid, sourceTable='magazyn_opakowania',
                nr_palety=code, sourceSpot='DOSTAWA', productName='Test packaging',
                quantity=100, packageForm='packaging', unit='szt')
    cursor.execute("INSERT INTO magazyn_dostawy (id,linia,status,supplier,lokalizacja_z,items) VALUES (%s,'AGRO','PUTAWAY_IN_PROGRESS','Test supplier','DOSTAWA',%s)",
                   (document_id, json.dumps([item])))
    conn.commit()
    conn.close()
    yield document_id, code, item
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM magazyn_dostawy WHERE id=%s', (document_id,))
    cursor.execute('DELETE FROM magazyn_opakowania WHERE nr_palety=%s', (code,))
    cursor.execute('DELETE FROM palety_historia WHERE nr_palety=%s', (code,))
    conn.commit()
    conn.close()


def delivery_snapshot(document_id, code):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT status,items FROM magazyn_dostawy WHERE id=%s', (document_id,))
    state, items = cursor.fetchone()
    cursor.execute('SELECT lokalizacja,stan_magazynowy FROM magazyn_opakowania WHERE nr_palety=%s', (code,))
    stock = cursor.fetchone()
    conn.close()
    return state, json.loads(items), stock


def test_putaway_commits_metadata_and_stock_together(app, pending_delivery):
    document_id, code, _ = pending_delivery
    result = AcceptanceService.accept_item(document_id, 'one', 'MS01', 'pytest', expected_status='PUTAWAY_IN_PROGRESS')
    assert result[0], result[1]
    state, items, stock = delivery_snapshot(document_id, code)
    assert state == 'COMPLETED'
    assert items[0]['putaway_confirmed_location'] == 'MS01'
    assert items[0]['pallet_status'] == 'STORED'
    assert items[0]['accepted']
    assert stock == ('MS01', 100)


def test_putaway_history_failure_rolls_back_everything(app, pending_delivery, monkeypatch):
    document_id, code, _ = pending_delivery
    before = delivery_snapshot(document_id, code)
    monkeypatch.setattr('app.services.warehouse_history.movement_recorder.MovementRecorder.record_movement', lambda *a, **k: False)
    assert not AcceptanceService.accept_item(document_id, 'one', 'MS01', 'pytest', expected_status='PUTAWAY_IN_PROGRESS')[0]
    assert delivery_snapshot(document_id, code) == before


@pytest.mark.parametrize('phase', ['SZKIC', 'AWIZOWANE', 'W_STREFIE_PRZYJEC'])
def test_early_delivery_phase_cannot_be_accepted(app, pending_delivery, phase):
    document_id, code, _ = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE magazyn_dostawy SET status=%s WHERE id=%s', (phase, document_id))
    conn.commit()
    conn.close()
    before = delivery_snapshot(document_id, code)
    assert not AcceptanceService.accept_item(document_id, 'one', 'MS01', 'pytest')[0]
    assert delivery_snapshot(document_id, code) == before


@pytest.mark.parametrize('quantity', [float('nan'), float('inf'), -1, 0])
def test_external_delivery_rejects_invalid_quantity(quantity):
    cursor = MagicMock()
    with pytest.raises(ValueError, match='Ilość'):
        ExternalDeliveryProcessor.process_reception(cursor, [dict(id='one', quantity=quantity)],
            'AGRO', 'Supplier', '', 'RAMPA', {}, None, [], 'pytest')
    cursor.execute.assert_not_called()


def test_external_delivery_cannot_claim_foreign_stock_id():
    cursor = MagicMock()
    with pytest.raises(ValueError, match='obcej palety'):
        ExternalDeliveryProcessor.process_reception(cursor, [dict(id='one', quantity=100, sourcePalletId=123)],
            'AGRO', 'Supplier', '', 'RAMPA', {}, None, [], 'pytest')
    cursor.execute.assert_not_called()


def test_external_delivery_cannot_remove_accepted_item():
    cursor = MagicMock()
    with pytest.raises(ValueError, match='usuwać'):
        ExternalDeliveryProcessor.process_reception(cursor, [], 'AGRO', 'Supplier', '', 'RAMPA', {},
            {'id': 'document'}, [dict(id='one', accepted=True)], 'pytest')
    cursor.execute.assert_not_called()


def test_putaway_rechecks_phase_after_lock(app, pending_delivery):
    document_id, code, _ = pending_delivery
    before = delivery_snapshot(document_id, code)
    result = AcceptanceService.accept_item(document_id, 'one', 'MS01', 'pytest', expected_status='OCZEKUJE')
    assert not result[0]
    assert delivery_snapshot(document_id, code) == before


@pytest.mark.parametrize('phase', ['SZKIC', 'AWIZOWANE'])
def test_staging_delivery_preserves_stock_reservation(pending_delivery, phase):
    from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
    document_id, code, _ = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute('UPDATE magazyn_dostawy SET status=%s WHERE id=%s', (phase, document_id))
        assert PalletLockManager.has_protected_block(cursor, code)
    finally:
        conn.rollback()
        conn.close()


def test_legacy_dispatch_history_failure_rolls_back_stock_and_archive(pending_delivery, monkeypatch):
    from app.services.warehouse_v2_service import WarehouseV2Service
    document_id, code, item = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_dostawy SET status='COMPLETED' WHERE id=%s", (document_id,))
    cursor.execute("UPDATE magazyn_opakowania SET lokalizacja='MS01' WHERE nr_palety=%s", (code,))
    conn.commit()
    conn.close()
    before = delivery_snapshot(document_id, code)
    connection = get_db_connection()
    raw_cursor = connection.cursor(dictionary=True)
    wrapper = MagicMock(wraps=connection)
    guarded_cursor = MagicMock(wraps=raw_cursor)
    def execute(sql, params=None):
        if 'INSERT INTO palety_historia' in sql:
            raise RuntimeError('Injected history failure')
        return raw_cursor.execute(sql, params)
    guarded_cursor.execute.side_effect = execute
    wrapper.cursor.return_value = guarded_cursor
    monkeypatch.setattr('app.services.warehouse_v2_service.get_db_connection', lambda: wrapper)
    assert not WarehouseV2Service.dispatch_pallet(item['sourcePalletId'], 'Opakowanie', 'pytest', linia='AGRO')[0]
    assert delivery_snapshot(document_id, code) == before
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM magazyn_archiwum WHERE nr_palety=%s', (code,))
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_completed_document_draft_is_not_counted(client, pending_delivery):
    document_id, code, item = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_dostawy SET status='COMPLETED' WHERE id=%s", (document_id,))
    conn.commit()
    conn.close()
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    before = delivery_snapshot(document_id, code)
    response = client.post('/magazyn-dostawy/api/draft/check', json={
        'drafts': [dict(hall='AGRO', document_id=document_id, items=[item])]})
    assert response.status_code == 200
    assert response.get_json()['counts'] == {}
    assert delivery_snapshot(document_id, code) == before


def test_consumed_pallet_draft_is_not_counted(client, pending_delivery):
    document_id, code, item = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE magazyn_opakowania SET stan_magazynowy=0 WHERE nr_palety=%s', (code,))
    conn.commit()
    conn.close()
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    response = client.post('/magazyn-dostawy/api/draft/check', json={
        'drafts': [dict(hall='AGRO', document_id='new', items=[item])]})
    assert response.status_code == 200
    assert response.get_json()['counts'].get('AGRO', 0) == 0


def test_suspended_order_blocks_same_section_only():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO plan_produkcji_agro (data_planu,sekcja,produkt,tonaz,status) VALUES (CURRENT_DATE,'Zasyp','Test suspended',100,'zawieszone')")
        suspended_id = cursor.lastrowid
        assert guard_section_start(cursor, 'plan_produkcji_agro', suspended_id, 'Zasyp') is None
        assert 'Test suspended' in guard_section_start(cursor, 'plan_produkcji_agro', suspended_id + 1000000, 'Zasyp')
        # Different sections remain independent parts of the production pipeline.
        cursor.execute("UPDATE plan_produkcji_agro SET status='zakończone' WHERE id=%s", (suspended_id,))
        assert guard_section_start(cursor, 'plan_produkcji_agro', suspended_id + 1000000, 'Zasyp') is None
    finally:
        conn.rollback()
        conn.close()


def test_two_pallets_cannot_claim_one_rack_slot():
    codes = ['TEST-RACK-' + uuid.uuid4().hex for _ in range(2)]
    location = 'R880102'
    conn = get_db_connection()
    cursor = conn.cursor()
    for code in codes:
        cursor.execute("INSERT INTO magazyn_surowce (nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES (%s,'Test rack',100,'MS01')", (code,))
    conn.commit()
    conn.close()
    def move(code):
        connection = get_db_connection()
        try:
            transaction = connection.cursor(dictionary=True)
            available, _ = check_rack_location_availability(location, current_nr_palety=code, product_name='Test rack', cursor=transaction)
            if not available:
                return False
            transaction.execute('UPDATE magazyn_surowce SET lokalizacja=%s WHERE nr_palety=%s', (location, code))
            connection.commit()
            return True
        finally:
            connection.rollback()
            connection.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert sorted(executor.map(move, codes)) == [False, True]
    finally:
        conn = get_db_connection()
        cursor = conn.cursor()
        for code in codes:
            cursor.execute('DELETE FROM magazyn_surowce WHERE nr_palety=%s', (code,))
        conn.commit()
        conn.close()


def test_reservation_ignores_empty_history_copy(app, pending_delivery):
    from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
    _, code, item = pending_delivery
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("INSERT INTO magazyn_opakowania(nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES(%s,'Old copy',0,'OCZEKUJĄCE')", (code,))
        old_id = cursor.lastrowid
        PalletLockManager.set_pallets_blocked(cursor, [item], 1)
        cursor.execute('SELECT id,is_blocked FROM magazyn_opakowania WHERE nr_palety=%s', (code,))
        rows = {row['id']: row['is_blocked'] for row in cursor.fetchall()}
        assert rows[item['sourcePalletId']] == 1
        assert not rows[old_id]
        cursor.execute('UPDATE magazyn_opakowania SET stan_magazynowy=100 WHERE id=%s', (old_id,))
        with pytest.raises(ValueError, match='Niejednoznaczna'):
            PalletLockManager.set_pallets_blocked(cursor, [item], 1)
    finally:
        conn.rollback()
        conn.close()


def test_reject_item_uses_sscc_even_when_source_id_is_wrong(app, pending_delivery):
    document_id, code, item = pending_delivery
    item.update(sourceSpot='RAMPA', originalSpot='MS01', sourcePalletId=-1)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE magazyn_dostawy SET supplier=NULL,items=%s WHERE id=%s", (json.dumps([item]), document_id))
    conn.commit()
    conn.close()
    result = AcceptanceService.reject_item(document_id, 'one', 'Return to sender', 'pytest')
    assert result[0], result[1]
    state, items, stock = delivery_snapshot(document_id, code)
    assert state == 'OCZEKUJE'
    assert items[0]['rejected']
    assert stock == ('MS01', 100)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT nr_palety,lokalizacja_docelowa FROM palety_historia WHERE nr_palety=%s AND akcja='TRANSFER_REJECT_ITEM'", (code,))
    assert cursor.fetchone() == (code, 'MS01')
    conn.close()


def test_reject_item_rolls_back_when_original_rack_is_occupied(app, pending_delivery):
    document_id, code, item = pending_delivery
    item.update(sourceSpot='RAMPA', originalSpot='R880102')
    occupied = 'TEST-REJECT-' + uuid.uuid4().hex
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO magazyn_surowce(nr_palety,nazwa,stan_magazynowy,lokalizacja) VALUES(%s,'Occupied',100,'R880102')", (occupied,))
    cursor.execute('UPDATE magazyn_dostawy SET items=%s WHERE id=%s', (json.dumps([item]), document_id))
    conn.commit()
    conn.close()
    try:
        before = delivery_snapshot(document_id, code)
        result = AcceptanceService.reject_item(document_id, 'one', 'No pallet', 'pytest')
        assert not result[0]
        assert 'zajęta' in result[1]
        assert delivery_snapshot(document_id, code) == before
    finally:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM magazyn_surowce WHERE nr_palety=%s', (occupied,))
        conn.commit()
        conn.close()
