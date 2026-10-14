"""A denied request must never reach the production action."""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, g

from app.core.function_permissions import register_function_permissions


@pytest.fixture
def permission_app():
    app = Flask(__name__)
    app.secret_key = 'isolated-permission-test'
    action = MagicMock(return_value='changed')
    app.add_url_rule('/suspend/<int:id>', endpoint='production.zawies_zlecenie',
                     view_func=action, methods=['POST'])
    app.add_url_rule('/close/<int:id>', endpoint='production.koniec_zlecenie',
                     view_func=lambda id: g.production_section, methods=['POST'])
    app.add_url_rule('/stage', endpoint='production.zasyp_etap_start',
                     view_func=action, methods=['POST'])
    app.add_url_rule('/folio', endpoint='production.agro_folio_add_roll',
                     view_func=action, methods=['POST'])
    app.add_url_rule('/downtime/<int:id>', endpoint='production.edytuj_przestoj_page',
                     view_func=action, methods=['POST'])
    app.add_url_rule('/bigbag/remove', endpoint='production.api_workowanie_bigbag_remove',
                     view_func=action, methods=['POST'])
    register_function_permissions(app)
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='AGRO')
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = ('Zasyp',)
    helpers = {'role_has_access': lambda key: key == 'agro.workowanie',
               'role_is_readonly': lambda key: False}
    with patch('app.core.production_permissions.get_db_connection', return_value=connection), patch(
            'app.core.function_permissions.configured_function_permission', return_value=None), patch(
            'app.core.contexts.inject_role_permissions', return_value=helpers):
        yield client, action, connection, helpers


@pytest.mark.parametrize('payload', [
    {'linia': 'AGRO'}, {'linia': 'AGRO', 'sekcja': 'Zasyp'},
    {'linia': 'AGRO', 'sekcja': 'Workowanie'},
])
def test_denied_real_section_cannot_be_bypassed(permission_app, payload):
    client, action, _, _ = permission_app
    assert client.post('/suspend/123', data=payload).status_code == 403
    action.assert_not_called()


def test_readonly_blocks_even_without_section(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    helpers['role_is_readonly'] = lambda key: True
    assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 403
    action.assert_not_called()


def test_other_hall_cannot_be_selected(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    assert client.post('/suspend/123', data={'linia': 'PSD'}).status_code == 403
    action.assert_not_called()


def test_authorized_order_without_ui_section_works(permission_app):
    client, action, connection, helpers = permission_app
    helpers['role_has_access'] = lambda key: key == 'agro.zasyp'
    assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 200
    action.assert_called_once_with(id=123)
    connection.close.assert_called_once()


def test_wrong_section_rejected_even_with_both_grants(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    assert client.post('/suspend/123', data={
        'linia': 'AGRO', 'sekcja': 'Workowanie'}).status_code == 403
    action.assert_not_called()


def test_missing_resource_denied(permission_app):
    client, action, connection, _ = permission_app
    connection.cursor.return_value.fetchone.return_value = None
    assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 404
    action.assert_not_called()


def test_database_failure_denies_without_mutation(permission_app):
    client, action, connection, _ = permission_app
    connection.cursor.return_value.execute.side_effect = RuntimeError('offline')
    assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 503
    action.assert_not_called()
    connection.close.assert_called_once()


def test_close_uses_server_owned_section(permission_app):
    client, _, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    assert client.post('/close/123', data={'linia': 'AGRO'}).data == b'Zasyp'


def test_stage_rejects_workowanie_plan(permission_app):
    client, action, connection, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    connection.cursor.return_value.fetchone.return_value = ('Workowanie',)
    assert client.post('/stage', data={'plan_id': '123', 'linia': 'AGRO'}).status_code == 403
    action.assert_not_called()


def test_fixed_function_checks_actual_page_with_json(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: key == 'agro.zasyp'
    assert client.post('/folio', json={'linia': 'AGRO', 'sekcja': 'Zasyp'}).status_code == 415
    action.assert_not_called()


def test_conflicting_query_and_form_halls_rejected(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    assert client.post('/suspend/123?linia=AGRO', data={'linia': 'PSD'}).status_code == 403
    action.assert_not_called()


def test_individual_page_deny_wins_over_role_allow(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    with client.session_transaction() as state:
        state['user_id'] = 17
    with patch('app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_overrides',
               return_value={'agro.zasyp': {'access': False, 'readonly': False}}):
        assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 403
    action.assert_not_called()


def test_individual_page_storage_failure_denies(permission_app):
    client, action, _, helpers = permission_app
    helpers['role_has_access'] = lambda key: True
    with client.session_transaction() as state:
        state['user_id'] = 17
    with patch('app.repositories.user_permission_override_repository.user_permission_override_repository.get_user_overrides',
               side_effect=RuntimeError('offline')):
        assert client.post('/suspend/123', data={'linia': 'AGRO'}).status_code == 403
    action.assert_not_called()


def test_downtime_edit_checks_original_before_new_section(permission_app):
    client, action, _, _ = permission_app
    with patch('app.repositories.downtime_repository.DowntimeRepository.get_downtime_by_id',
               return_value={'linia': 'AGRO', 'sekcja': 'Zasyp'}):
        assert client.post('/downtime/12', data={'linia': 'AGRO', 'sekcja': 'Workowanie'}).status_code == 403
    action.assert_not_called()


def test_bigbag_remove_resolves_owning_plan(permission_app):
    client, action, connection, _ = permission_app
    connection.cursor.return_value.fetchone.side_effect = [(123,), ('Zasyp',)]
    assert client.post('/bigbag/remove', json={'entry_id': 9}).status_code == 403
    action.assert_not_called()


@pytest.mark.parametrize('allowed, expected', [(False, 403), (True, 302)])
def test_real_suspend_route_obeys_resource_permission(client, allowed, expected):
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='AGRO', login='permission-test', pracownik_id=1)
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = ('Zasyp',)
    with patch('app.core.production_permissions.get_db_connection', return_value=connection), patch(
            'app.core.contexts.inject_role_permissions', return_value={
                'role_has_access': lambda key: allowed, 'role_is_readonly': lambda key: False}), patch(
            'app.core.function_permissions.configured_function_permission', return_value=None), patch(
            'app.services.planning.status.PlanningStatusService.suspend_plan', return_value=(False, 'test')) as suspend:
        response = client.post('/zawies_zlecenie/123', data={'linia': 'AGRO'})
    assert response.status_code == expected
    if allowed:
        suspend.assert_called_once_with(123, linia='AGRO')
    else:
        suspend.assert_not_called()


def test_every_configurable_production_write_has_a_page_policy():
    from app.core.function_permissions import OPERATOR_ACTIONS
    from app.core.production_permissions import ORDER_ACTIONS, ZASYP_PLAN_ACTIONS, FIXED_SECTIONS
    mapped = ORDER_ACTIONS | ZASYP_PLAN_ACTIONS | set(FIXED_SECTIONS) | {
        'potwierdz_dosypke', 'anuluj_dosypke', 'zglos_przestoj_page',
        'edytuj_przestoj_page', 'usun_przestoj',
        # Laboratory release uses its own role guard and the function ACL.
        'api_zwolnij_mieszalnik'}
    assert {key.split('.', 1)[1] for key in OPERATOR_ACTIONS
            if key.startswith('production.')} <= mapped
