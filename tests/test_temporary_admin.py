# cspell:words szwarark boczkmar tojson
"""Time-limited privileges remain subordinate to the authoritative account."""
from unittest.mock import MagicMock, patch

from flask import Flask, jsonify, render_template_string, session
import pytest

from app.core.security_hardening import register_role_integrity_check
from app.core.temporary_admin import register_temporary_admin
from app.decorators import roles_required


@pytest.fixture
def switch_app():
    app = Flask(__name__)
    app.secret_key = 'temporary-elevation-isolated-test'
    register_role_integrity_check(app)
    register_temporary_admin(app)

    @app.get('/menu')
    def menu():
        return render_template_string('{{ temporary_admin | tojson }}')

    @app.post('/protected')
    @roles_required('masteradmin')
    def protected():
        return jsonify(success=True)

    connection = MagicMock()
    row = ['lider', 'ALL', 1]
    connection.cursor.return_value.fetchone.side_effect = lambda: tuple(row)
    with patch('app.core.security_hardening.get_db_connection', return_value=connection), patch(
        'app.core.temporary_admin.audit_log') as audit, patch('time.time', return_value=10000) as clock:
        yield app, app.test_client(), row, audit, clock


def sign_in(client, login='SzwarArk', role='lider'):
    with client.session_transaction() as state:
        state.update(zalogowany=True, user_id=8, login=login, rola=role, grupa='ALL')
    response = client.get('/menu')
    import json
    return json.loads(response.get_data(as_text=True))


def toggle(client, token, action='enable'):
    return client.post('/auth/temporary-masteradmin/' + action,
                       headers={'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest'})


@pytest.mark.parametrize('login', ['SzwarArk', 'szwarark', 'BoczkMar', 'BOCZKMAR'])
def test_only_named_leaders_can_elevate_for_exactly_ten_minutes(switch_app, login):
    _, client, _, audit, clock = switch_app
    menu = sign_in(client, login)
    assert menu['eligible'] and not menu['active']
    assert client.post('/protected').status_code == 403
    response = toggle(client, menu['csrf'])
    assert response.status_code == 200
    assert response.headers['X-RP-Temporary-Admin'] == 'active'
    assert response.json['expires_at'] == 10600
    assert client.post('/protected').status_code == 200
    clock.return_value = 10599
    assert client.post('/protected').status_code == 200
    clock.return_value = 10600
    assert client.post('/protected').status_code == 403
    assert client.get('/auth/temporary-masteradmin/status').json['role'] == 'lider'
    assert audit.call_count == 2


def test_expiry_is_enforced_even_when_database_role_check_is_cached(switch_app):
    _, client, _, _, clock = switch_app
    token = sign_in(client)['csrf']
    toggle(client, token)
    clock.return_value = 10599
    assert client.post('/protected').status_code == 200
    clock.return_value = 10601
    assert client.post('/protected').status_code == 403


def test_database_sync_keeps_active_elevation_and_repeated_click_does_not_extend_it(switch_app):
    _, client, _, _, clock = switch_app
    token = sign_in(client)['csrf']
    toggle(client, token)
    clock.return_value = 10090
    assert client.post('/protected').status_code == 200
    assert toggle(client, token).json['expires_at'] == 10600


def test_manual_return_restores_leader_and_records_audit(switch_app):
    _, client, _, audit, _ = switch_app
    token = sign_in(client)['csrf']
    toggle(client, token)
    response = toggle(client, token, 'disable')
    assert response.json['role'] == 'lider' and not response.json['active']
    assert client.post('/protected').status_code == 403
    assert 'Wyłączono ręcznie' in audit.call_args.args[1]


@pytest.mark.parametrize('login', ['ordinary', 'SzwarArk-extra', 'BoczkMar-extra'])
def test_other_accounts_cannot_use_endpoint_even_with_valid_csrf(switch_app, login):
    _, client, _, _, _ = switch_app
    assert not sign_in(client, login)['eligible']
    with client.session_transaction() as state:
        state['_temporary_admin_csrf'] = 'valid-test-token'
    assert toggle(client, 'valid-test-token').status_code == 403


def test_only_post_with_session_csrf_can_change_role(switch_app):
    _, client, _, _, _ = switch_app
    token = sign_in(client)['csrf']
    assert client.get('/auth/temporary-masteradmin/enable').status_code == 405
    assert toggle(client, '').status_code == 403
    assert toggle(client, 'wrong').status_code == 403
    assert toggle(client, token).status_code == 200


@pytest.mark.parametrize('changed', [('pracownik', 'AGRO', 1), ('lider', 'ALL', 0)])
def test_activation_rechecks_account_and_rejects_demotion_or_deactivation(switch_app, changed):
    _, client, row, _, _ = switch_app
    token = sign_in(client)['csrf']
    row[:] = changed
    assert toggle(client, token).status_code in (401, 403)
    assert client.post('/protected').status_code != 200


def test_named_database_masteradmin_uses_leader_by_default_without_changing_database(switch_app):
    _, client, row, _, _ = switch_app
    row[0] = 'masteradmin'
    menu = sign_in(client, role='masteradmin')
    assert menu['role'] == 'lider'
    assert toggle(client, menu['csrf']).json['active']
    assert row[0] == 'masteradmin'


def test_ordinary_permanent_masteradmin_is_unchanged(switch_app):
    _, client, row, _, _ = switch_app
    row[0] = 'masteradmin'
    menu = sign_in(client, 'other-admin', 'masteradmin')
    assert not menu['eligible']
    assert client.post('/protected').status_code == 200


def test_grant_cannot_be_transferred_to_another_user_or_have_longer_deadline(switch_app):
    _, client, _, _, _ = switch_app
    token = sign_in(client)['csrf']
    toggle(client, token)
    with client.session_transaction() as state:
        grant = dict(state['_temporary_masteradmin'])
        grant['user_id'] = 99
        state['_temporary_masteradmin'] = grant
    assert client.post('/protected').status_code == 403
    toggle(client, token)
    with client.session_transaction() as state:
        grant = dict(state['_temporary_masteradmin'])
        grant['expires'] += 1
        state['_temporary_masteradmin'] = grant
    assert client.post('/protected').status_code == 403


def test_logged_out_session_cannot_elevate(switch_app):
    _, client, _, _, _ = switch_app
    assert toggle(client, 'any').status_code == 401
