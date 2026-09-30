"""Regression tests for security guarantees introduced by the full audit."""

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


def test_authenticated_mutation_without_origin_is_rejected(app, monkeypatch):
    endpoint = '/__audit_mutation'
    if 'audit_mutation' not in app.view_functions:
        app.add_url_rule(endpoint, 'audit_mutation', lambda: 'ok', methods=['POST'])

    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    app.config['TESTING'] = False
    app.testing = False

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['user_id'] = 999
        sess['login'] = 'audit-user'
        sess['rola'] = 'pracownik'

    response = client.post(endpoint)
    assert response.status_code == 403


def test_legacy_admin_raw_socket_printer_test_is_replaced(app):
    from app.core.legacy_print_hardening import secure_admin_zpl_test

    assert app.view_functions['admin.admin_zpl_test'] is secure_admin_zpl_test


def test_legacy_admin_bridge_status_uses_secure_client(app):
    from app.core.legacy_print_hardening import secure_admin_printer_server_status

    assert app.view_functions['admin.admin_printer_server_status'] is secure_admin_printer_server_status
