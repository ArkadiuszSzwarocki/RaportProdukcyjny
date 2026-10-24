# cspell:words delenv EJUS
"""Adversarial authorization and transport regression tests without external writes."""
from unittest.mock import MagicMock, patch
import ssl
import pytest
from flask import Flask, g, session
from werkzeug.routing import Rule
from app.core.scanner_permissions import enforce_scanner_permissions, scanner_resource_read_allowed
from app.core.logistics_permissions import enforce_logistics_permissions
from app.core.middleware import enforce_csrf_origin_check
from scripts.upload_backup import upload_ftp


@pytest.fixture
def security_app():
    app = Flask(__name__)
    app.secret_key = 'isolated-security-regression-key'
    return app


@pytest.mark.parametrize('endpoint', ['scanner.move', 'scanner.dispatch', 'scanner.restore_pallet', 'scanner.print_label'])
def test_scanner_denied_grant_never_reads_stock(security_app, endpoint):
    with security_app.test_request_context('/scanner', method='POST', json={'linia': 'AGRO', 'type': 'Wyrób Gotowy'}):
        from flask import request
        request.url_rule = Rule('/security-test', endpoint=endpoint)
        with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
                'app.core.scanner_permissions.get_db_connection') as connect:
            assert enforce_scanner_permissions()[1] == (401 if endpoint == 'scanner.print_label' else 403)
            connect.assert_not_called()


@pytest.mark.parametrize('row, expected', [
    (None, 404), ({'id': 1, 'nr_palety': 'TEST', 'linia': 'PSD'}, 200),
    ({'id': 1, 'nr_palety': 'OTHER', 'linia': 'AGRO'}, 400),
])
def test_scanner_checks_server_owned_identity(security_app, row, expected):
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = row
    with security_app.test_request_context('/scanner', method='POST', json={
            'linia': 'AGRO', 'type': 'Wyrób Gotowy', 'surowiec_id': 1, 'nr_palety': 'TEST'}):
        from flask import request
        request.url_rule = Rule('/security-test', endpoint='scanner.move')
        with patch('app.core.scanner_permissions._page_allowed', return_value=True), patch(
                'app.core.scanner_permissions.get_db_connection', return_value=connection):
            result = enforce_scanner_permissions()
            assert (200 if result is None else result[1]) == expected
    connection.close.assert_called_once()


def test_scanner_database_failure_denies_operation(security_app):
    with security_app.test_request_context('/scanner', method='POST', json={'linia': 'AGRO', 'type': 'Wyrób Gotowy'}):
        from flask import request
        request.url_rule = Rule('/security-test', endpoint='scanner.move')
        with patch('app.core.scanner_permissions._page_allowed', return_value=True), patch(
                'app.core.scanner_permissions.get_db_connection', side_effect=RuntimeError('unavailable')):
            assert enforce_scanner_permissions()[1] == 503


def test_scanner_lookup_authorizes_actual_resource_hall(security_app):
    from app.services.scanner.scanner_item_normalizer import ScannerItemNormalizer
    with security_app.test_request_context('/scanner?linia=AGRO', method='POST', json={'linia': 'AGRO', 'type': 'Wyrób Gotowy'}):
        session['zalogowany'] = True
        with patch('app.core.scanner_permissions._page_allowed', side_effect=lambda line, *_args, **_kwargs: line == 'AGRO'):
            assert not scanner_resource_read_allowed({'linia': 'PSD'})
            assert scanner_resource_read_allowed({'linia': 'AGRO'})
            normalized = ScannerItemNormalizer.normalize_pallet({'id': 1, 'linia': 'PSD', 'ilosc': 10})
            assert not scanner_resource_read_allowed(normalized)


def test_dispatch_cannot_fallback_after_authorized_pallet_disappears(security_app):
    from app.services.scanner.scanner_movement_service import ScannerMovementService
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = None
    with security_app.test_request_context('/scanner'):
        g.warehouse_resource = {'table': 'magazyn_agro_surowce', 'id': 1, 'nr_palety': 'TEST'}
        with patch('app.services.scanner_service.get_db_connection', return_value=connection):
            result = ScannerMovementService.dispatch_to_production(1, 1, 'security-test', 'AGRO')
        assert not result[0]
        assert connection.cursor.return_value.execute.call_count == 1
        connection.commit.assert_not_called()


@pytest.mark.parametrize('endpoint', ['magazyn_dostawy.zapisz_dostawe', 'magazyn_dostawy.anuluj_dostawe'])
def test_delivery_document_hall_does_not_restrict_shared_warehouse(security_app, endpoint):
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {'linia': 'PSD'}
    with security_app.test_request_context('/delivery', method='POST', json={'linia': 'AGRO', 'id': 'DOC'}):
        from flask import request
        request.url_rule = Rule('/security-test', endpoint=endpoint)
        request.view_args = {'dostawa_id': 'DOC'}
        with patch('app.core.logistics_permissions._page_allowed', return_value=True), patch(
                'app.core.logistics_permissions.get_db_connection', return_value=connection):
            assert enforce_logistics_permissions() is None


@pytest.mark.parametrize('endpoint', ['magazyn_dostawy.zapisz_dostawe', 'magazyn_dostawy.przyjmij_wg'])
def test_delivery_requires_authenticated_warehouse_session(security_app, endpoint):
    with security_app.test_request_context('/delivery?linia=AGRO', method='POST', json={'items': []}):
        from flask import request
        request.url_rule = Rule('/security-test', endpoint=endpoint)
        assert enforce_logistics_permissions()[1] == 403


@pytest.mark.parametrize('origin, status', [
    ('https://warehouse.example', 200), ('http://warehouse.example', 403),
    ('https://attacker.example', 403), ('null', 403), (None, 403),
])
def test_csrf_origin_in_production_mode(security_app, monkeypatch, origin, status):
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    security_app.before_request(enforce_csrf_origin_check(security_app))
    security_app.add_url_rule('/write', view_func=lambda: 'OK', methods=['POST'])
    client = security_app.test_client()
    with client.session_transaction(base_url='https://warehouse.example') as state:
        state['zalogowany'] = True
    headers = {'Origin': origin} if origin else {}
    assert client.post('/write', base_url='https://warehouse.example', headers=headers, json={}).status_code == status


def test_backup_encrypts_credentials_and_data(tmp_path):
    backup = tmp_path / 'test.sql'
    backup.write_text('isolated test data', encoding='utf-8')
    connection = MagicMock()
    with patch('ftplib.FTP_TLS', return_value=connection) as tls:
        assert upload_ftp(str(backup), 'backup.example', 'test', 'test')
    context = tls.call_args.kwargs['context']
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    names = [call[0] for call in connection.method_calls]
    assert names.index('login') < names.index('prot_p') < names.index('storbinary')


def test_backup_certificate_failure_never_sends_data(tmp_path):
    connection = MagicMock()
    connection.login.side_effect = ssl.SSLCertVerificationError('untrusted certificate')
    with patch('ftplib.FTP_TLS', return_value=connection):
        assert not upload_ftp(str(tmp_path / 'test.sql'), 'backup.example', 'test', 'test')
    connection.storbinary.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize('readonly, access, line', [(True, True, 'AGRO'), (False, False, 'AGRO'), (False, True, 'PSD')])
def test_production_dispatch_cannot_bypass_production_page_and_hall_grants(security_app, readonly, access, line):
    from app.blueprints.scanner.base import scanner_bp
    security_app.register_blueprint(scanner_bp)
    client = security_app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='AGRO')
    helpers = {'role_has_access': lambda _key: access, 'role_is_readonly': lambda _key: readonly}
    with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
            'app.core.scanner_permissions.get_db_connection') as connect, patch(
            'app.services.scanner_service.ScannerService.dispatch_to_production') as move:
        response = client.post('/agro/scanner/dispatch', json={'linia': line, 'type': 'Surowiec', 'surowiec_id': 1, 'ilosc': 1, 'zbiornik': 'BB03'})
    assert response.status_code == 403
    connect.assert_not_called()
    move.assert_not_called()


def test_label_preview_cannot_inject_printer_commands(security_app):
    from app.blueprints.scanner.base import label_location
    with security_app.test_request_context('/label_location?loc=R01%5EFS%5EXA%5EJUS%7EJA'):
        with patch('app.blueprints.scanner.base.render_template', return_value='OK') as render:
            assert label_location() == 'OK'
    zpl = render.call_args.kwargs['zpl_string']
    assert '^JUS' not in zpl and '~JA' not in zpl
    assert zpl.count('^XA') == 1 and zpl.count('^XZ') == 1


def test_missing_label_identifier_is_json_not_reflected_html(security_app):
    from app.blueprints.scanner.base import label
    with security_app.test_request_context('/label/test'):
        with patch('app.services.scanner_service.ScannerService.get_label_data', return_value=None):
            response, status = label('<img src=x onerror=alert(1)>')
    assert status == 404 and response.mimetype == 'application/json'


def test_label_retains_actual_finished_goods_hall():
    from app.services.scanner.scanner_label_service import ScannerLabelService
    row = {'id': 1, 'linia': 'PSD', 'nr_palety': 'SUR000001790591646672',
           'nazwa': 'Soja', 'stan_magazynowy': 10, 'lokalizacja': 'MGW01'}
    assert ScannerLabelService.build_label_dict(MagicMock(), row, 'AGRO', 'PAL', 'WYRÓB GOTOWY', True)['linia'] == 'PSD'


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_printer_bridge_never_follows_redirects(method, monkeypatch):
    from app.services.print_server import PrintServer
    monkeypatch.setenv('PRINTER_BRIDGE_AUTOSTART', 'false')
    printer = PrintServer()
    response = MagicMock(status_code=302, headers={'Location': 'http://attacker.example'})
    with patch('app.services.print_server.requests.request', return_value=response) as send:
        result, _bridge = printer._request_bridge(method, '/status', allow_redirects=True)
    assert result is response
    assert send.call_args.kwargs['allow_redirects'] is False
    send.assert_called_once()


@pytest.mark.parametrize('table, row', [
    ('magazyn_surowce', {'id': 1, 'nr_palety': 'TEST'}),
    ('magazyn_palety', {'id': 1, 'nr_palety': 'TEST', 'linia': 'PSD'}),
    ('magazyn_palety', {'id': 1, 'nr_palety': 'TEST'}),
])
def test_draft_cannot_lock_foreign_or_unknown_hall_stock(security_app, table, row):
    from app.services.magazyn_dostawy.commands.pallet_lock_manager import PalletLockManager
    connection = MagicMock()
    connection.cursor.return_value.fetchall.return_value = [row]
    with security_app.test_request_context('/draft', method='POST', json={'linia': 'AGRO', 'type': 'Wyrób Gotowy'}):
        session.update(zalogowany=True, rola='pracownik', grupa='AGRO')
        helpers = {'role_has_access': lambda _key: True, 'role_is_readonly': lambda _key: False}
        with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
                'app.services.magazyn_dostawy.commands.pallet_lock_manager.get_db_connection', return_value=connection):
            ok, _message = PalletLockManager.lock_draft_pallets([{
                'sourceTable': table, 'sourcePalletNo': 'TEST', 'sourcePalletId': 1}], 'AGRO', 'security-test')
    assert not ok
    assert not any(str(call.args[0]).startswith('UPDATE') for call in connection.cursor.return_value.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_sync_draft_rejects_unauthenticated_stock_mutation(security_app):
    from app.services.magazyn_dostawy.commands.draft_pallet_sync_service import DraftPalletSyncService
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchone.side_effect = [None, None, None, None, {'id': 1, 'linia': 'PSD', 'waga_netto': 10}]
    with security_app.test_request_context('/draft', method='POST', json={'linia': 'AGRO', 'type': 'Wyrób Gotowy'}):
        session.update(zalogowany=False, rola='pracownik', grupa='AGRO')
        helpers = {'role_has_access': lambda _key: True, 'role_is_readonly': lambda _key: False}
        with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
                'app.services.magazyn_dostawy.commands.draft_pallet_sync_service.get_db_connection', return_value=connection):
            ok, _message = DraftPalletSyncService.sync_draft_pallets([{'nr_palety': 'TEST'}], 'AGRO', 'security-test')
    assert not ok
    assert not any(str(call.args[0]).startswith('UPDATE') for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once()


def test_reprint_shared_stock_without_hall_queues_authoritative_label(security_app):
    from app.core.legacy_print_hardening import secure_reprint_labels
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {'ip': '127.0.0.1', 'nazwa': 'Test'}
    with security_app.test_request_context('/reprint', method='POST', json={'printer_id': 1, 'nr_palety': 'TEST'}):
        session.update(zalogowany=True, rola='pracownik', grupa='AGRO')
        helpers = {'role_has_access': lambda _key: True, 'role_is_readonly': lambda _key: False}
        with patch('app.core.contexts.inject_role_permissions', return_value=helpers), patch(
                'app.core.legacy_print_hardening.get_db_connection', return_value=connection), patch(
                'app.core.legacy_print_hardening._load_authoritative_label', return_value={'linia': None, 'nr_palety': 'TEST', 'typ': 'OPAKOWANIE'}), patch(
                'app.core.legacy_print_hardening.get_printer') as printer:
            printer.return_value.queue_print_job.return_value = (True, 'queued')
            response = secure_reprint_labels()
            assert response.json['success']
    printer.return_value.queue_print_job.assert_called_once()
