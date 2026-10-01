"""Regression tests for security guarantees introduced by the full audit.

This suite is intentionally kept close to the hardened entry points so audit
remediation cannot silently regress during later refactors. The file is also
part of the final audit CI checkpoint for PR #17.
"""

import inspect
from io import BytesIO

from cryptography.fernet import Fernet


def test_printer_bridge_protected_routes_require_token(monkeypatch):
    from printer_server import server

    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'audit-test-token')
    previous_testing = server.app.config.get('TESTING')
    server.app.config['TESTING'] = False
    try:
        client = server.app.test_client()
        assert client.get('/status').status_code == 200
        assert client.get('/printers').status_code == 401

        response = client.get(
            '/printers',
            headers={'Authorization': 'Bearer audit-test-token'},
        )
        assert response.status_code == 200
        assert response.get_json()['success'] is True
    finally:
        server.app.config['TESTING'] = previous_testing


def test_printer_bridge_shutdown_is_disabled_by_default(monkeypatch):
    from printer_server import server

    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'audit-test-token')
    monkeypatch.delenv('PRINTER_BRIDGE_ALLOW_SHUTDOWN', raising=False)
    previous_testing = server.app.config.get('TESTING')
    server.app.config['TESTING'] = False
    try:
        response = server.app.test_client().post(
            '/shutdown',
            headers={'Authorization': 'Bearer audit-test-token'},
        )
        assert response.status_code == 403
    finally:
        server.app.config['TESTING'] = previous_testing


def test_printer_bridge_rejects_unconfigured_arbitrary_target(monkeypatch):
    from printer_server import server

    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'audit-test-token')
    previous_testing = server.app.config.get('TESTING')
    server.app.config['TESTING'] = False
    original_map = dict(server.PRINTER_IP_MAP)
    server.PRINTER_IP_MAP.clear()
    try:
        response = server.app.test_client().post(
            '/drukuj-zpl',
            headers={'Authorization': 'Bearer audit-test-token'},
            json={'ip': '127.0.0.1', 'dane': '^XA^XZ'},
        )
        assert response.status_code == 400
        assert response.get_json()['success'] is False
    finally:
        server.PRINTER_IP_MAP.clear()
        server.PRINTER_IP_MAP.update(original_map)
        server.app.config['TESTING'] = previous_testing


def test_printer_bridge_pdf_rejects_unconfigured_local_printer(monkeypatch):
    from printer_server import server

    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'audit-test-token')
    previous_testing = server.app.config.get('TESTING')
    server.app.config['TESTING'] = False
    original_map = dict(server.PRINTER_IP_MAP)
    server.PRINTER_IP_MAP.clear()
    server.PRINTER_IP_MAP['Approved Printer'] = '10.0.0.10'
    try:
        response = server.app.test_client().post(
            '/drukuj-pdf',
            headers={'Authorization': 'Bearer audit-test-token'},
            data={
                'drukarka': 'Unapproved Local Printer',
                'file': (BytesIO(b'%PDF-1.4\n%%EOF'), 'audit.pdf'),
            },
            content_type='multipart/form-data',
        )
        assert response.status_code == 400
        assert response.get_json()['success'] is False
    finally:
        server.PRINTER_IP_MAP.clear()
        server.PRINTER_IP_MAP.update(original_map)
        server.app.config['TESTING'] = previous_testing


def test_production_factory_never_registers_debug_url_map(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.setenv('ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'S' * 64)
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('ENABLE_DEBUG_ROUTES', 'true')
    monkeypatch.setenv('ENABLE_BACKGROUND_DAEMONS', 'false')
    monkeypatch.setenv('SKIP_DB_SETUP', 'true')

    from app.core.factory import create_app

    application = create_app(config_secret_key='S' * 64, init_db=False)
    rules = {str(rule.rule) for rule in application.url_map.iter_rules()}
    assert '/__debug/url_map' not in rules


def test_query_string_print_token_is_rejected(app):
    response = app.test_client().get('/?print_token=legacy-secret')
    assert response.status_code == 400
    assert response.get_json()['success'] is False


def test_untrusted_forwarded_for_is_stripped(app, monkeypatch):
    monkeypatch.setenv('TRUST_PROXY_HEADERS', 'false')
    endpoint = '/__audit_remote_addr'
    if 'audit_remote_addr' not in app.view_functions:
        from app.core.security_hardening import current_client_ip
        app.add_url_rule(endpoint, 'audit_remote_addr', current_client_ip, methods=['GET'])

    response = app.test_client().get(
        endpoint,
        headers={'X-Forwarded-For': '203.0.113.99'},
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) != '203.0.113.99'


def test_trusted_proxy_sets_remote_addr_but_hides_raw_forwarded_header(monkeypatch):
    from flask import Flask, request
    from app.core.security_hardening import apply_proxy_policy

    monkeypatch.setenv('TRUST_PROXY_HEADERS', 'true')
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', '1')

    proxy_app = Flask(__name__)

    @proxy_app.get('/ip')
    def _ip_probe():
        raw_forwarded = request.headers.get('X-Forwarded-For', '')
        return f'{request.remote_addr}|{raw_forwarded}'

    apply_proxy_policy(proxy_app)
    response = proxy_app.test_client().get(
        '/ip',
        headers={'X-Forwarded-For': '203.0.113.77'},
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == '203.0.113.77|'


def test_authenticated_mutation_without_origin_is_rejected(app, monkeypatch):
    """Exercise CSRF independently from the DB-backed session validity check."""
    endpoint = '/__audit_mutation'
    if 'audit_mutation' not in app.view_functions:
        app.add_url_rule(endpoint, 'audit_mutation', lambda: 'ok', methods=['POST'])

    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    app.config['TESTING'] = False
    app.testing = False
    monkeypatch.setattr('app.core.middleware.is_session_active', lambda _session_id: True)
    monkeypatch.setattr('app.core.middleware.touch_active_session', lambda **_kwargs: True)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 999
        sess['login'] = 'audit-user'
        sess['rola'] = 'pracownik'
        sess['session_tracking_id'] = 'audit-session'
        sess['session_active_cached'] = True
        sess['last_session_active_check'] = 0

    response = client.post(endpoint)
    assert response.status_code == 403


def test_authenticated_cross_origin_mutation_is_rejected(app, monkeypatch):
    endpoint = '/__audit_cross_origin_mutation'
    if 'audit_cross_origin_mutation' not in app.view_functions:
        app.add_url_rule(endpoint, 'audit_cross_origin_mutation', lambda: 'ok', methods=['POST'])

    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    app.config['TESTING'] = False
    app.testing = False
    monkeypatch.setattr('app.core.middleware.is_session_active', lambda _session_id: True)
    monkeypatch.setattr('app.core.middleware.touch_active_session', lambda **_kwargs: True)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 998
        sess['login'] = 'audit-origin-user'
        sess['rola'] = 'pracownik'
        sess['session_tracking_id'] = 'audit-origin-session'
        sess['session_active_cached'] = True
        sess['last_session_active_check'] = 0

    response = client.post(
        endpoint,
        headers={'Origin': 'https://evil.example'},
    )
    assert response.status_code == 403


def test_legacy_admin_raw_socket_printer_test_is_replaced(app):
    from inspect import unwrap
    from app.core.legacy_print_hardening import secure_admin_zpl_test

    view = app.view_functions['admin.admin_zpl_test']
    assert unwrap(view) is secure_admin_zpl_test
    assert getattr(view, '_audit_zpl_masteradmin_required', False)


def test_legacy_admin_bridge_status_uses_secure_client(app):
    from inspect import unwrap
    from app.core.legacy_print_hardening import secure_admin_printer_server_status

    view = app.view_functions['admin.admin_printer_server_status']
    assert unwrap(view) is secure_admin_printer_server_status
    assert getattr(view, '_audit_printer_status_permission', False)


def test_legacy_printer_settings_socket_probe_is_replaced(app):
    from app.core.runtime_security_hardening import secure_admin_printer_settings

    assert app.view_functions['admin.admin_ustawienia_drukarki'] is secure_admin_printer_settings


def test_plaintext_login_password_qr_is_disabled(app):
    from flask import session

    view = app.view_functions['admin.admin_qr_generator_drukuj']
    with app.test_request_context(
        '/admin/ustawienia/qr-generator/drukuj',
        method='POST',
        json={'mode': 'login', 'login': 'audit', 'password': 'Secret123!'},
    ):
        session['zalogowany'] = True
        session['rola'] = 'masteradmin'
        response, status = view()

    assert status == 410
    assert response.get_json()['success'] is False


def test_runtime_database_switch_requires_masteradmin_and_explicit_opt_in(app, monkeypatch):
    from flask import session

    view = app.view_functions['admin.admin_secret_db_switch']
    monkeypatch.delenv('ALLOW_RUNTIME_DB_SWITCH', raising=False)

    with app.test_request_context('/admin/sekretna-baza/switch', method='POST'):
        session['zalogowany'] = True
        session['rola'] = 'admin'
        response, status = view()
        assert status == 403
        assert response.get_json()['success'] is False

    with app.test_request_context('/admin/sekretna-baza/switch', method='POST'):
        session['zalogowany'] = True
        session['rola'] = 'masteradmin'
        response, status = view()
        assert status == 403
        assert response.get_json()['success'] is False


def test_acceptance_service_insecure_print_thread_is_replaced(app):
    from app.core.legacy_print_hardening import secure_accept_item
    from app.services.magazyn_dostawy.acceptance_service import AcceptanceService

    assert AcceptanceService.accept_item is secure_accept_item


def test_pallet_creation_print_threads_use_bounded_executor(app):
    from app.core.legacy_print_hardening import _ExecutorBackedThread
    from app.services.pallets import pallet_creation_service

    assert pallet_creation_service.threading.Thread is _ExecutorBackedThread


def test_mqtt_simulator_is_admin_only(app):
    from flask import session

    view = app.view_functions['api.mqtt_simulate']
    with app.test_request_context('/api/mqtt_simulate', method='POST', json={}):
        session['zalogowany'] = True
        session['user_id'] = 44
        session['login'] = 'ordinary-user'
        session['rola'] = 'pracownik'
        response, status = view()

    assert status == 403
    assert response.get_json()['success'] is False


def test_auth_module_contains_no_legacy_bridge_or_username_privilege_bypass():
    from app.blueprints.auth import base as auth_base

    source = inspect.getsource(auth_base)
    assert 'verify=False' not in source
    assert "request.headers.get('X-Forwarded-For'" not in source
    assert "login_field.lower().strip() == 'masteradmin'" not in source
