# cspell:words sscc zaladunki
"""Denied warehouse mutations must not reach a state-changing service."""
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def warehouse_context(client):
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='PSD', login='warehouse-test',
                     pracownik_id=1, selected_hall_view='AGRO')
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {
        'id': 123, 'nr_palety': 'TEST-123', 'linia': 'PSD'}
    helpers = {'role_has_access': lambda key: key == 'psd.magazyn',
               'role_is_readonly': lambda key: False}
    with patch('app.core.warehouse_permissions.get_db_connection', return_value=connection), patch(
            'app.core.function_permissions.configured_function_permission', return_value=None), patch(
            'app.core.contexts.inject_role_permissions', return_value=helpers), patch(
            'app.services.warehouse_v2_service.WarehouseV2Service.move_pallet', return_value=(True, 'OK')) as move:
        yield client, connection, helpers, move


def post_move(client, **changes):
    payload = {'id': 123, 'type': 'Surowiec', 'location': 'R010101', 'linia': 'PSD'}
    payload.update(changes)
    return client.post('/warehouse-v2/api/pallet/move', json=payload)


def test_denied_page_blocks_without_optional_section(warehouse_context):
    client, _, helpers, move = warehouse_context
    helpers['role_has_access'] = lambda key: False
    assert post_move(client).status_code == 403
    move.assert_not_called()


def test_readonly_page_blocks_json_write(warehouse_context):
    client, _, helpers, move = warehouse_context
    helpers['role_is_readonly'] = lambda key: True
    assert post_move(client).status_code == 403
    move.assert_not_called()


def test_truck_dispatch_cannot_bypass_hall_permission(warehouse_context):
    client, _, _, _ = warehouse_context
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.dispatch_pallet_to_vehicle') as dispatch:
        assert client.post('/warehouse-v2/api/zaladunki/dispatch', json={'linia': 'AGRO'}).status_code == 403
    dispatch.assert_not_called()


def test_readonly_truck_history_is_filtered_and_dispatch_denied(warehouse_context):
    client, _, helpers, _ = warehouse_context
    helpers['role_is_readonly'] = lambda key: True
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.get_dispatches_history', return_value=[]) as history, patch(
            'app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.dispatch_pallet_to_vehicle') as dispatch:
        assert client.get('/warehouse-v2/api/zaladunki/history?linia=PSD').status_code == 200
        history.assert_called_once_with(limit=200, linia='PSD')
        assert client.post('/warehouse-v2/api/zaladunki/dispatch', json={'linia': 'PSD'}).status_code == 403
    dispatch.assert_not_called()


def test_truck_lookup_checks_actual_pallet_hall(warehouse_context):
    client, _, _, _ = warehouse_context
    with patch('app.blueprints.warehouse_v2.zaladunki_routes.dispatch_service.lookup_pallet_for_dispatch', return_value={'linia': 'AGRO'}):
        assert client.get('/warehouse-v2/api/zaladunki/lookup-pallet?linia=PSD&code=TEST').status_code == 403


def test_order_creation_denied_without_section(warehouse_context):
    client, _, helpers, _ = warehouse_context
    helpers['role_has_access'] = lambda key: False
    with patch('app.blueprints.warehouse_v2.api_orders._order_service.create_order') as create:
        assert client.post('/warehouse-v2/api/orders/create', json={'items': []}).status_code == 403
        create.assert_not_called()


def test_readonly_orders_can_be_viewed_but_not_created(warehouse_context):
    client, _, helpers, _ = warehouse_context
    helpers['role_is_readonly'] = lambda key: True
    with patch('app.blueprints.warehouse_v2.api_orders._order_service.get_all_orders', return_value=[]), patch(
            'app.blueprints.warehouse_v2.api_orders._order_service.create_order') as create:
        assert client.get('/warehouse-v2/api/orders').status_code == 200
        assert client.post('/warehouse-v2/api/orders/create', json={'items': []}).status_code == 403
        create.assert_not_called()


def test_allowed_order_creation_remains_available(warehouse_context):
    client, _, _, _ = warehouse_context
    with patch('app.blueprints.warehouse_v2.api_orders._order_service.create_order', return_value=(True, 'OK', 123)) as create:
        assert client.post('/warehouse-v2/api/orders/create', json={'items': [{'surowiec_nazwa': 'TEST', 'ilosc_kg': 10}]}).status_code == 201
        create.assert_called_once()


def test_foreign_hall_blocks_even_when_page_is_granted(warehouse_context):
    client, _, helpers, move = warehouse_context
    helpers['role_has_access'] = lambda key: True
    assert post_move(client, linia='AGRO').status_code == 403
    move.assert_not_called()


def test_authorized_move_uses_validated_hall(warehouse_context):
    client, connection, _, move = warehouse_context
    assert post_move(client).status_code == 200
    move.assert_called_once_with(123, 'Surowiec', 'R010101', 'warehouse-test', 'PSD', amount_to_move=None)
    connection.close.assert_called_once()


def test_record_in_another_hall_is_rejected(warehouse_context):
    client, connection, _, move = warehouse_context
    connection.cursor.return_value.fetchone.return_value['linia'] = 'AGRO'
    assert post_move(client).status_code == 403
    move.assert_not_called()


def test_missing_record_cannot_trigger_cross_hall_fallback(warehouse_context):
    client, connection, _, move = warehouse_context
    connection.cursor.return_value.fetchone.return_value = None
    assert post_move(client).status_code == 404
    move.assert_not_called()


def test_lookup_failure_stops_mutation(warehouse_context):
    client, connection, _, move = warehouse_context
    connection.cursor.return_value.execute.side_effect = RuntimeError('offline')
    assert post_move(client).status_code == 503
    move.assert_not_called()


def test_query_cannot_disagree_with_json_hall(warehouse_context):
    client, _, _, move = warehouse_context
    result = client.post('/warehouse-v2/api/pallet/move?linia=AGRO', json={
        'id': 123, 'type': 'Surowiec', 'location': 'R010101', 'linia': 'PSD'})
    assert result.status_code == 403
    move.assert_not_called()


def test_sscc_cannot_select_a_different_resource(warehouse_context):
    client, _, _, move = warehouse_context
    assert post_move(client, sscc='ANOTHER').status_code == 400
    move.assert_not_called()


def test_invalid_json_denied_before_handler(warehouse_context):
    client, _, _, move = warehouse_context
    assert client.post('/warehouse-v2/api/pallet/move', json=[]).status_code == 400
    move.assert_not_called()


def test_suspend_json_hall_confusion_is_rejected(client):
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='ALL', login='test',
                     pracownik_id=1, selected_hall_view='AGRO')
    with patch('app.core.function_permissions.configured_function_permission', return_value=None), patch(
            'app.services.planning.status.PlanningStatusService.suspend_plan') as suspend:
        result = client.post('/zawies_zlecenie/123', json={'linia': 'PSD'})
    assert result.status_code == 415
    suspend.assert_not_called()


@pytest.mark.parametrize('route, service', [
    ('archive', 'archive_pallet'), ('dispatch', 'dispatch_pallet'),
    ('rename', 'rename_pallet'), ('update-weight', 'update_weight'),
    ('update-packaging', 'update_packaging_type'), ('return-to-raw', 'return_pallet_to_raw'),
    ('toggle-block', 'toggle_block')])
def test_other_pallet_operations_cannot_skip_page_denial(warehouse_context, route, service):
    client, _, helpers, _ = warehouse_context
    helpers['role_has_access'] = lambda key: False
    with client.session_transaction() as state:
        state.update(rola='admin', grupa='ALL')
    with patch('app.services.warehouse_v2_service.WarehouseV2Service.' + service) as mutation:
        result = client.post('/warehouse-v2/api/pallet/' + route, json={
            'id': 123, 'type': 'Surowiec', 'linia': 'PSD', 'name': 'new',
            'weight': 10, 'packaging_type': 'Big Bag'})
    assert result.status_code == 403
    mutation.assert_not_called()


def test_function_grant_cannot_override_readonly_page(warehouse_context):
    client, _, helpers, move = warehouse_context
    helpers['role_is_readonly'] = lambda key: True
    with patch('app.core.function_permissions.configured_function_permission', return_value=True):
        assert post_move(client).status_code == 403
    move.assert_not_called()


def test_restoration_checks_stored_hall(warehouse_context):
    client, connection, _, _ = warehouse_context
    connection.cursor.return_value.fetchone.return_value = {'linia': 'AGRO'}
    with patch('app.services.warehouse_v2_service.WarehouseV2Service.restore_pallet_from_archive') as restore:
        result = client.post('/warehouse-v2/api/archiwum/restore/9', json={'linia': 'PSD', 'waga': 20})
    assert result.status_code == 403
    restore.assert_not_called()


def test_osip_record_requires_osip_hall_context(warehouse_context):
    client, connection, helpers, move = warehouse_context
    helpers['role_has_access'] = lambda key: key == 'osip.magazyn'
    with client.session_transaction() as state:
        state.update(grupa='OSIP', rola='magazynier')
    connection.cursor.return_value.fetchone.return_value['linia'] = 'OSIP'
    assert post_move(client, linia='OSIP').status_code == 200
    move.assert_called_once()


@pytest.mark.parametrize('explicit', [None, False, True])
def test_osip_page_inherits_legacy_grant_only_until_explicitly_configured(app, explicit):
    from app.core.contexts import inject_role_permissions
    config = {'psd.magazyn': {'magazynier': {'access': True, 'readonly': False}}}
    if explicit is not None:
        config['osip.magazyn'] = {'magazynier': {'access': explicit, 'readonly': False}}
    with app.test_request_context('/'), patch('app.core.contexts._get_role_permissions', return_value=config):
        from flask import session
        session.update(zalogowany=True, rola='magazynier', grupa='OSIP')
        assert inject_role_permissions()['role_has_access']('osip.magazyn') is (explicit is not False)


def test_global_quality_lock_requires_all_warehouse_grants(warehouse_context):
    client, _, _, _ = warehouse_context
    with patch('app.services.warehouse_v2_service.WarehouseV2Service.toggle_block') as toggle:
        result = client.post('/warehouse-v2/api/pallet/toggle-block', json={
            'id': 123, 'type': 'Surowiec', 'linia': 'PSD'})
    assert result.status_code == 403
    toggle.assert_not_called()


@pytest.mark.parametrize('exists', [True, False])
def test_quality_lock_uses_verified_table_and_never_matches_unrelated_ids(app, exists):
    from flask import g
    from app.services.warehouse_v2.pallet_status_service import PalletStatusService
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = {'id': 123, 'nr_palety': 'TEST-123', 'is_blocked': 0} if exists else None
    with app.test_request_context('/'), patch(
            'app.services.warehouse_v2.pallet_status_service.get_db_connection', return_value=connection):
        g.warehouse_resource = {'table': 'magazyn_palety_agro', 'id': 123, 'nr_palety': 'TEST-123'}
        success, _ = PalletStatusService.toggle_block(123, 'Wyrób Gotowy', 'test', linia='AGRO')
    assert success is exists
    selects = [call.args[0] for call in cursor.execute.call_args_list if call.args[0].startswith('SELECT')]
    assert len(selects) == 1 and 'FROM magazyn_palety_agro ' in selects[0]
    updates = [call for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    assert len(updates) == (7 if exists else 0)
    assert all('WHERE nr_palety = %s' in call.args[0] and call.args[1] == (1, 'TEST-123') for call in updates)
    if not exists:
        connection.commit.assert_not_called()


@pytest.mark.parametrize('module, class_name, operation', [
    ('app.services.warehouse_v2_service', 'WarehouseV2Service', 'move_pallet'),
    ('app.services.warehouse_v2.pallet_relocation_service', 'PalletRelocationService', 'move_pallet'),
    ('app.services.warehouse_v2.pallet_modification_service', 'PalletModificationService', 'update_weight')])
def test_removed_verified_pallet_cannot_fall_back_to_foreign_stock(app, module, class_name, operation):
    import importlib
    from flask import g
    service = getattr(importlib.import_module(module), class_name)
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = None
    with app.test_request_context('/'), patch(module + '.get_db_connection', return_value=connection):
        g.warehouse_resource = {'table': 'magazyn_palety_agro', 'id': 123, 'nr_palety': 'TEST-123'}
        if operation == 'move_pallet':
            result = service.move_pallet(123, 'Wyrób Gotowy', 'MGW02', 'test', linia='AGRO')
        else:
            result = service.update_weight(123, 'Wyrób Gotowy', 20, 'test', linia='AGRO')
    assert result[0] is False
    queries = [call.args[0] for call in cursor.execute.call_args_list]
    stock_queries = [query for query in queries if 'magazyn_dozwolone_lokalizacje' not in query]
    assert all(query.startswith('SELECT') for query in queries)
    assert stock_queries and all('FROM magazyn_palety_agro ' in query for query in stock_queries)
    connection.commit.assert_not_called()
