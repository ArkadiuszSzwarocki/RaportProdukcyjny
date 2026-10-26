"""Pinned tests stay isolated; local switching changes only the connection."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, session
from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader


@pytest.mark.parametrize('accept', ['text/html', 'application/json'])
def test_disabled_switch_returns_to_ui_or_json_without_switching(monkeypatch, accept):
    from app.core.runtime_security_hardening import _masteradmin_runtime_db_switch
    monkeypatch.delenv('ALLOW_RUNTIME_DB_SWITCH', raising=False)
    app = Flask(__name__)
    app.secret_key = 'local-ui-test'
    app.add_url_rule('/db', endpoint='admin.admin_secret_db', view_func=lambda: 'Database page')
    original = MagicMock()
    with app.test_request_context('/switch', method='POST', headers={'Accept': accept}):
        session.update(zalogowany=True, rola='masteradmin')
        response = app.make_response(_masteradmin_runtime_db_switch(original)())
        if accept == 'text/html':
            assert response.status_code == 303 and response.location == '/db'
            assert session['_flashes']
        else:
            assert response.status_code == 403 and response.json['success'] is False
    original.assert_not_called()


def test_database_page_disables_every_switch_for_local_test_mode():
    env = Environment(loader=ChoiceLoader([DictLoader({'layout.html': '{% block content %}{% endblock %}'}),
        FileSystemLoader(str(Path(__file__).parents[1] / 'templates'))]), autoescape=True)
    env.globals['url_for'] = lambda endpoint: '/switch'
    html = env.get_template('admin/sekretna_baza.html').render(current_db='biblioteka_testowa',
        allowed_databases=['biblioteka', 'biblioteka_testowa'], can_switch_db=False, test_instance=True)
    assert 'class="btn btn-primary"' not in html
    assert html.count(' disabled>') == 2
    assert 'biblioteka_testowa' in html


def test_local_mode_ignores_and_does_not_overwrite_saved_database(monkeypatch):
    from app.core import database
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    with patch('builtins.open', side_effect=AssertionError('Saved production selection must not be touched')):
        assert database._load_persisted_database_name() is None
        database._persist_database_name('biblioteka_testowa')


def test_test_mode_rejects_production_database_before_connecting(monkeypatch):
    from app.core import database
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    monkeypatch.setitem(database.DB_CONFIG, 'database', 'biblioteka_testowa')
    with patch('mysql.connector.connect') as connect:
        with pytest.raises(ValueError):
            database.set_active_database_name('biblioteka')
    connect.assert_not_called()
    assert database.DB_CONFIG['database'] == 'biblioteka_testowa'


def test_wrong_database_prevents_test_instance_start(monkeypatch):
    from app.core.instance_mode import configure_instance
    from app.config import DB_CONFIG
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    monkeypatch.setitem(DB_CONFIG, 'database', 'biblioteka')
    with pytest.raises(RuntimeError, match='biblioteka_testowa'):
        configure_instance(Flask(__name__))


def test_test_session_is_separate_from_production(monkeypatch):
    from app.core.instance_mode import configure_instance
    from app.config import DB_CONFIG
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    monkeypatch.setitem(DB_CONFIG, 'database', 'biblioteka_testowa')
    app = Flask(__name__)
    configure_instance(app)
    assert app.config['SESSION_COOKIE_NAME'] == 'raport_test_session'


def test_failed_qnap_connection_never_falls_back_to_localhost(monkeypatch):
    import mysql.connector
    from app.core import database
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    monkeypatch.setattr(database, 'is_local', True)
    monkeypatch.setitem(database.DB_CONFIG, 'host', 'qnap.example.test')
    with patch.object(database, '_get_or_create_pool', return_value=None), patch(
            'mysql.connector.connect', side_effect=mysql.connector.Error('offline')) as connect:
        with pytest.raises(mysql.connector.Error):
            database.get_db_connection(retries=1)
    assert [call.kwargs['host'] for call in connect.call_args_list] == ['qnap.example.test']


def test_test_mode_blocks_email_before_dns_or_connection(monkeypatch):
    from app.core.network_security import secure_smtp_connection
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    with patch('app.core.network_security._resolve_smtp_target') as resolve:
        with pytest.raises(ValueError):
            secure_smtp_connection('smtp.example.test', 587, 'TLS')
    resolve.assert_not_called()


def test_test_mode_blocks_printer_queue_and_direct_output(monkeypatch):
    from app.services.print_server import PrintServer
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    printer = PrintServer.__new__(PrintServer)
    with patch('app.db.get_db_connection') as connect, patch('socket.create_connection') as socket:
        assert printer.queue_print_job('^XA^XZ')[0] is False
        assert printer.send_direct_tcp('^XA^XZ', '192.0.2.10')[0] is False
        assert printer._send_to_bridge_once({}, 'test')[0] is False
    connect.assert_not_called()
    socket.assert_not_called()


def test_test_mode_does_not_queue_office_prints(monkeypatch):
    from app.services import office_print_service
    from app.services.tracked_movement_print import submit
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    with patch.object(office_print_service._PRINT_EXECUTOR, 'submit') as send:
        assert office_print_service.trigger_office_print(2) is False
        assert office_print_service.trigger_office_print_url('/report') is False
        with pytest.raises(ValueError):
            submit(None, 'test', 'printer', 'operator', [])
    send.assert_not_called()


def test_test_mode_never_publishes_machine_commands(monkeypatch):
    from app.services import mqtt_service
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    client = MagicMock()
    monkeypatch.setattr(mqtt_service, '_active_mqtt_client', client)
    assert mqtt_service.publish_command('machine', {'start': 1}) is False
    client.publish.assert_not_called()


def test_locked_instance_keeps_ui_switch_disabled_even_with_opt_in(monkeypatch):
    from app.core.runtime_security_hardening import runtime_database_switch_enabled
    monkeypatch.setenv('APP_INSTANCE_MODE', 'test')
    monkeypatch.setenv('ALLOW_RUNTIME_DB_SWITCH', 'true')
    assert runtime_database_switch_enabled() is False


@pytest.mark.parametrize('target', ['biblioteka', 'biblioteka_testowa', 'biblioteka_test'])
def test_local_switch_verifies_connection_without_schema_or_account_writes(monkeypatch, target):
    from app.core import database
    monkeypatch.setenv('APP_INSTANCE_MODE', 'local')
    monkeypatch.setenv('DB_NAME_LOCKED', 'false')
    monkeypatch.setitem(database.DB_CONFIG, 'database', 'biblioteka_testowa')
    monkeypatch.setattr(database, '_DB_POOL', object())
    with patch('mysql.connector.connect') as connect, patch.object(database, '_persist_database_name') as persist, patch('app.core.database_setup.setup_database') as setup:
        assert database.set_active_database_name(target) == target
    assert connect.call_args.kwargs['database'] == target
    connect.return_value.cursor.assert_not_called()
    connect.return_value.close.assert_called_once()
    persist.assert_called_once_with(target)
    setup.assert_not_called()
    assert database._DB_POOL is None
    assert database.get_active_database_name() == target


def test_failed_local_switch_preserves_previous_database(monkeypatch):
    from app.core import database
    monkeypatch.setenv('APP_INSTANCE_MODE', 'local')
    monkeypatch.setenv('DB_NAME_LOCKED', 'false')
    monkeypatch.setitem(database.DB_CONFIG, 'database', 'biblioteka_testowa')
    old_pool = object()
    monkeypatch.setattr(database, '_DB_POOL', old_pool)
    with patch('mysql.connector.connect', side_effect=RuntimeError('Unavailable')), patch.object(database, '_persist_database_name') as persist:
        with pytest.raises(RuntimeError):
            database.set_active_database_name('biblioteka')
    assert database.get_active_database_name() == 'biblioteka_testowa'
    assert database._DB_POOL is old_pool
    persist.assert_not_called()


def test_local_switch_requires_masteradmin_and_does_not_copy_accounts(monkeypatch):
    import inspect
    from flask import Blueprint
    from app.blueprints.admin import system
    from app.core.runtime_security_hardening import _masteradmin_runtime_db_switch
    monkeypatch.setenv('APP_INSTANCE_MODE', 'local')
    monkeypatch.setenv('DB_NAME_LOCKED', 'false')
    monkeypatch.setenv('ALLOW_RUNTIME_DB_SWITCH', 'true')
    app = Flask(__name__)
    app.secret_key = 'local-switch-test'
    bp = Blueprint('admin', __name__)
    system.register_admin_system_routes(bp, list_online_users=lambda: [])
    app.register_blueprint(bp)
    handler = _masteradmin_runtime_db_switch(inspect.unwrap(app.view_functions['admin.admin_secret_db_switch']))
    with patch.object(system, 'set_active_database_name', return_value='biblioteka') as switch, patch.object(system, 'get_db_connection') as connect:
        with app.test_request_context('/switch', method='POST', data={'database': 'biblioteka'}, headers={'Accept': 'application/json'}):
            session.update(zalogowany=True, rola='operator', user_id=4)
            assert app.make_response(handler()).status_code == 403
        switch.assert_not_called()
        with app.test_request_context('/switch', method='POST', data={'database': 'biblioteka'}):
            session.update(zalogowany=True, rola='masteradmin', user_id=4)
            response = handler()
            assert response.status_code == 303 and response.location == '/login'
            assert 'user_id' not in session and 'rola' not in session
        switch.assert_called_once_with('biblioteka', verify_connection=True)
        connect.assert_not_called()


def test_local_database_page_offers_switches():
    env = Environment(loader=ChoiceLoader([DictLoader({'layout.html': '{% block content %}{% endblock %}'}),
        FileSystemLoader(str(Path(__file__).parents[1] / 'templates'))]), autoescape=True)
    env.globals['url_for'] = lambda endpoint: '/switch'
    html = env.get_template('admin/sekretna_baza.html').render(current_db='biblioteka_testowa',
        allowed_databases=['biblioteka', 'biblioteka_testowa', 'biblioteka_test'], can_switch_db=True, test_instance=True)
    assert html.count('class="btn btn-primary"') == 2
    assert html.count(' disabled>') == 1



def test_local_mode_keeps_integrations_active_and_cookie_separate(monkeypatch):
    from app.core.instance_mode import configure_instance, is_test_instance
    from app.config import DB_CONFIG
    from app.services import mqtt_service, office_print_service
    monkeypatch.setenv('APP_INSTANCE_MODE', 'local')
    monkeypatch.setitem(DB_CONFIG, 'database', 'biblioteka')
    assert is_test_instance() is False
    app = Flask(__name__)
    configure_instance(app)
    assert app.config['SESSION_COOKIE_NAME'] == 'raport_test_session'
    client = MagicMock()
    monkeypatch.setattr(mqtt_service, '_active_mqtt_client', client)
    assert mqtt_service.publish_command('test-topic', {'test': 1}) is True
    client.publish.assert_called_once()
    with patch.object(office_print_service, '_printer_assignment', return_value='test-printer'), patch.object(office_print_service._PRINT_EXECUTOR, 'submit') as enqueue:
        office_print_service.trigger_office_print_url('/report')
    enqueue.assert_called_once()
