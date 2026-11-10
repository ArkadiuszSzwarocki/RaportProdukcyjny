import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
from app.services.magazyn_dostawy.receipt_difference import receipt_quantity, require_issuer
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService


@pytest.mark.parametrize('value,reason', [(0, 'x'), (-1, 'x'), (1001, 'x'), ('NaN', 'x'),
                                        ('Infinity', 'x'), ('bad', 'x'), (800, '')])
def test_invalid_receipt_quantity(value, reason):
    with pytest.raises(ValueError):
        receipt_quantity(1000, value, reason)


def test_decimal_quantities_conserve_stock():
    assert receipt_quantity('27.8', '25,5', 'Różnica') == (25.5, 2.3)
    assert receipt_quantity(1000, None, '') == (1000, 0)


def test_original_issuer_must_approve():
    require_issuer({'return_approval_login': 'Issuer'}, 'issuer')
    with pytest.raises(ValueError, match='wydający'):
        require_issuer({'return_approval_login': 'Issuer'}, 'receiver')


@pytest.mark.parametrize('failure', [None, 'history', 'stock_changed', 'myisam'])
def test_partial_receipt_conserves_quantity_and_creates_blocked_return(failure):
    item = dict(id='item', sourcePalletId=11, sourcePalletNo='MOTHER', nr_palety='MOTHER',
                sourceTable='magazyn_surowce', sourceSpot='MS01', targetSpot='MP01',
                productName='Mąka', quantity=1000, netWeight=1000, unit='kg')
    document = dict(id='doc', created_by='issuer', supplier='', linia='AGRO',
                    status='OCZEKUJE', lokalizacja_z='MS01', lokalizacja_do='MP01', items=json.dumps([item]))
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.lastrowid = 12

    def one():
        sql = cur.execute.call_args.args[0]
        if 'SELECT * FROM magazyn_dostawy' in sql:
            return document
        return None

    def rows():
        sql = cur.execute.call_args.args[0]
        if 'information_schema.TABLES' in sql:
            return [dict(TABLE_NAME=name, ENGINE='MyISAM' if failure == 'myisam' else 'InnoDB')
                    for name in ('magazyn_surowce', 'magazyn_dostawy', 'palety_historia')]
        if 'FROM magazyn_surowce' in sql:
            return [dict(id=11, nr_palety='MOTHER', nazwa='Mąka', lokalizacja='MS01', is_blocked=1,
                         stan_magazynowy=900 if failure == 'stock_changed' else 1000)]
        return []

    cur.fetchone.side_effect = one
    cur.fetchall.side_effect = rows
    with ExitStack() as stack:
        for name, value in {
            'app.services.magazyn_dostawy.acceptance_service.get_db_connection': conn,
            'app.utils.location_validator.validate_registered_warehouse_location': (True, None),
            'app.utils.pallet_receipt_rules.ensure_unique_stock_code': 'MOTHER',
            'app.utils.pallet_receipt_rules.lock_receipt_registry': None,
            'app.utils.surowiec_validator.is_valid_surowiec': True,
            'app.services.magazyn_dostawy.acceptance_service.PalletLockManager.has_quality_or_manual_block': False,
            'app.services.magazyn_dostawy.acceptance_service.PalletLockManager.has_active_osip_transfer': False,
            'app.services.magazyn_dostawy.acceptance_service.PalletLockManager.set_pallets_blocked': None,
            'app.services.warehouse_history.movement_recorder.MovementRecorder.record_movement': failure != 'history',
            'app.repositories.movement_document_repository.MovementDocumentRepository.queue_completed': None,
        }.items():
            stack.enter_context(patch(name, return_value=value))
        result = AcceptanceService.accept_item('doc', 'item', 'MP01', 'receiver',
                                               accepted_quantity=800, quantity_reason='Nie przyjęto części')
    if failure:
        assert not result[0], result
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        return
    assert result[0], result
    conn.commit.assert_called_once()
    calls = cur.execute.call_args_list
    stock_update = next(call.args[1] for call in calls if call.args[0].strip().startswith('UPDATE magazyn_surowce'))
    assert stock_update[0] == 800
    child_insert = next(call for call in calls if call.args[0].startswith('INSERT INTO magazyn_surowce'))
    assert 200 in child_insert.args[1]
    assert 'OCZEKUJĄCE' in child_insert.args[1]
    return_insert = next(call.args[1] for call in calls if call.args[0].startswith('INSERT INTO magazyn_dostawy'))
    child = json.loads(return_insert[3])[0]
    assert child['quantity'] == 200
    assert child['return_approval_login'] == 'issuer'
    assert child['targetSpot'] == 'MS01'
    assert child['sourcePalletId'] == 12
    assert child['nr_palety'] != 'MOTHER'
    assert child['accepted'] is False
    saved = next(json.loads(call.args[1][0])[0] for call in calls
                 if call.args[0].strip().startswith('UPDATE magazyn_dostawy'))
    assert saved['accepted_quantity'] + saved['unaccepted_quantity'] == saved['original_quantity']
    assert saved['netWeight'] == 800
    assert saved['return_document_id'] == result[2]['return_document_id']


def test_receiver_cannot_accept_pending_return_through_direct_service():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = dict(
        id='return', status='OCZEKUJE', items=json.dumps([
            dict(id='pending', return_approval_login='issuer', targetSpot='MS01')]))
    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=conn):
        result = AcceptanceService.accept_item('return', 'pending', 'MS01', 'receiver')
    assert not result[0]
    assert 'wydający' in result[1]
    conn.commit.assert_not_called()
    assert not any(call.args[0].strip().startswith(('UPDATE', 'INSERT'))
                   for call in conn.cursor.return_value.execute.call_args_list)


def test_report_contains_discrepancy_and_escapes_reason():
    from app.services.warehouse_reports.pdf.delivery_pdf_builder import DeliveryPdfBuilder
    from app.services.warehouse_reports.warehouse_activity_query_service import WarehouseActivityQueryService
    item = dict(productName='Mąka', nr_palety='SSCC', accepted=True, original_quantity=1000,
                accepted_quantity=800, unaccepted_quantity=200, netWeight=1000,
                return_document_id='return-doc', quantity_reason='<script>test</script>')
    assert WarehouseActivityQueryService.extract_item_qty(item) == 800
    with patch('app.services.warehouse_reports.pdf.delivery_pdf_builder.PdfRendererService.render_html_or_fallback') as render:
        DeliveryPdfBuilder.generate(dict(id='doc', order_ref='ref', status='COMPLETED', linia='AGRO'), [item])
    html = render.call_args.args[0]
    assert 'Wydano: 1000; przyjęto: 800; nie przyjęto: 200' in html
    assert '&lt;script&gt;' in html
    assert '<script>test</script>' not in html
