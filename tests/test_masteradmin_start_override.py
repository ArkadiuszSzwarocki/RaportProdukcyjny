# cspell:words onsubmit
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from flask import Blueprint, Flask, session, url_for

from app.services.planning.start_guard import guard_section_start


@pytest.mark.parametrize('role', ['masteradmin', 'admin', 'lider', 'pracownik'])
@pytest.mark.parametrize('section', ['Zasyp', 'Workowanie', 'Czyszczenie', 'Bufor'])
def test_server_override_restricted_to_masteradmin_and_requested_sections(app, role, section):
    cursor = MagicMock()
    cursor.fetchall.return_value = [(1, 'Inne', 'w toku')]
    with app.test_request_context('/start'):
        session['rola'] = role
        if role == 'masteradmin' and section in ('Zasyp', 'Workowanie'):
            assert guard_section_start(cursor, 'plan_produkcji_agro', 2, section, override=True) is None
        else:
            with pytest.raises(ValueError):
                guard_section_start(cursor, 'plan_produkcji_agro', 2, section, override=True)
        assert guard_section_start(cursor, 'plan_produkcji_agro', 2, section) is not None


@pytest.mark.parametrize('role', ['masteradmin', 'admin', 'lider'])
@pytest.mark.parametrize('section', ['Zasyp', 'Workowanie', 'Czyszczenie'])
@pytest.mark.parametrize('status', ['zaplanowane', 'zawieszone', 'wstrzymane'])
def test_override_button_visibility(app, role, section, status):
    env = app.jinja_env.overlay()
    env.globals = dict(env.globals, url_for=lambda endpoint, **kw: '/start')
    p = [None] * 32
    p[0:4] = [2, 'Produkt', 100, status]
    html = env.get_template('dashboard/_masteradmin_start_override.html').render(
        p=p, role_lc=role, is_readonly=False, sekcja=section, linia='AGRO', unfinished_section_orders=[(1, 'Inne', 'w toku')])
    assert ('name="override_start_rule"' in html) == (role == 'masteradmin' and section in ('Zasyp', 'Workowanie'))
    if role == 'masteradmin' and section in ('Zasyp', 'Workowanie'):
        assert 'data-start-confirm=' in html
        assert 'data-confirm=' not in html
        assert 'onsubmit="return confirmStartOrder(' in html



@pytest.mark.parametrize('role', ['masteradmin', 'admin'])
def test_route_override_preserves_other_running_orders_and_is_audited(role):
    from app.blueprints.production.orders import register_production_order_routes
    isolated_app = Flask(__name__)
    isolated_app.secret_key = 'test-override-only'
    blueprint = Blueprint('production', __name__)
    register_production_order_routes(blueprint, lambda: '/')
    isolated_app.register_blueprint(blueprint)
    client = isolated_app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, login='pytest', rola=role, grupa='ALL')
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.return_value = ('Test', 100, 'Zasyp', date(2026, 10, 11), 'NORMAL', 'zawieszone', 0)
    cursor.fetchall.return_value = [(1, 'Inne', 'w toku'), (2, 'Test', 'zawieszone')]
    with client.application.test_request_context():
        path = url_for('production.start_zlecenie', id=2)
    with patch('app.blueprints.production.orders.get_db_connection', return_value=connection), patch(
        'app.blueprints.production.orders.audit_log') as audit, patch('app.db.create_notifications'), patch('app.db.refresh_bufor_queue'):
        response = client.post(path, data={'linia': 'PSD', 'override_start_rule': '1'})
    updates = [call.args[0] for call in cursor.execute.call_args_list if call.args[0].startswith('UPDATE')]
    if role == 'masteradmin':
        assert response.status_code == 302
        assert any("SET status='w toku'" in sql for sql in updates)
        assert not any("SET status='zaplanowane'" in sql for sql in updates)
        assert any('pominięto blokadę' in str(call) for call in audit.call_args_list)
    else:
        assert response.status_code == 403
        assert updates == []
