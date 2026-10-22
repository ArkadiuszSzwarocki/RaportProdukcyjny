"""Shared warehouse material must not inherit production hall restrictions."""
from unittest.mock import MagicMock, patch
import pytest
from flask import Flask, session, g, request
from werkzeug.routing import Rule
from app.core.scanner_permissions import enforce_scanner_permissions, scanner_resource_read_allowed
from app.core.warehouse_permissions import enforce_warehouse_write
from app.services.scanner.scanner_item_normalizer import ScannerItemNormalizer


@pytest.fixture
def app():
    instance = Flask(__name__)
    instance.secret_key = 'shared-stock-test'
    return instance


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
@pytest.mark.parametrize('role,group,line', [('pracownik', 'PSD', 'AGRO'), ('magazynier', 'AGRO', 'PSD'), ('laborant', 'OSIP', 'ALL')])
def test_material_move_ignores_hall_and_page_grants(app, kind, role, group, line):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'linia': 'OSIP'}
    with app.test_request_context('/scanner', method='POST', json={
            'type': kind, 'linia': line, 'surowiec_id': 7, 'nr_palety': 'TEST7', 'lokalizacja': 'R01-01'}):
        session.update(zalogowany=True, rola=role, grupa=group)
        request.url_rule = Rule('/scanner', endpoint='scanner.move')
        with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
                'app.core.scanner_permissions.get_db_connection', return_value=conn):
            assert enforce_scanner_permissions() is None
            assert g.warehouse_resource['id'] == 7
    conn.close.assert_called_once()


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
def test_shared_lookup_has_no_production_owner(app, kind):
    row = ScannerItemNormalizer.normalize_lookup_item(
        {'id': 7, 'nazwa': 'Kalka', 'linia': 'PSD', 'ilosc': 10},
        inventory_type=kind, inventory_key='TEST', code_prefix='TEST',
        can_dispatch=False, can_split=False, can_print_label=True)
    assert row['linia'] is None
    with app.test_request_context('/scanner', method='POST', json={'linia': 'AGRO'}):
        session.update(zalogowany=True, rola='pracownik', grupa='AGRO')
        with patch('app.core.scanner_permissions._page_allowed', return_value=False):
            assert scanner_resource_read_allowed(row)


@pytest.mark.parametrize('endpoint', ['scanner.lookup', 'scanner.scanner_ui', 'scanner.pallet_suggestions', 'scanner.printer_status'])
def test_scanner_entry_available_without_hall_grant(app, endpoint):
    with app.test_request_context('/scanner', method='POST', json={}):
        session.update(zalogowany=True, rola='pracownik', grupa='PSD')
        request.url_rule = Rule('/scanner', endpoint=endpoint)
        with patch('app.core.scanner_permissions._page_allowed', return_value=False):
            assert enforce_scanner_permissions() is None


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
def test_panel_move_uses_shared_stock(app, kind):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'linia': 'PSD'}
    with app.test_request_context('/api/pallet/move', method='POST', json={
            'id': 7, 'type': kind, 'linia': 'AGRO', 'location': 'R01-01'}):
        session.update(zalogowany=True, rola='pracownik', grupa='AGRO')
        request.url_rule = Rule('/api/pallet/move', endpoint='warehouse_v2.move_pallet')
        with patch('app.core.warehouse_permissions._page_allowed', return_value=False), patch(
                'app.core.warehouse_permissions.get_db_connection', return_value=conn):
            assert enforce_warehouse_write() is None
            assert g.warehouse_resource['nr_palety'] == 'TEST7'


def test_identity_validation_remains_required(app):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'OTHER', 'linia': 'PSD'}
    with app.test_request_context('/scanner', method='POST', json={
            'type': 'Opakowanie', 'surowiec_id': 7, 'nr_palety': 'TEST7'}):
        session['zalogowany'] = True
        request.url_rule = Rule('/scanner', endpoint='scanner.move')
        with patch('app.core.scanner_permissions.get_db_connection', return_value=conn):
            assert enforce_scanner_permissions()[1] == 400


def test_shared_move_requires_login(app):
    with app.test_request_context('/scanner', method='POST', json={'type': 'Opakowanie'}):
        request.url_rule = Rule('/scanner', endpoint='scanner.move')
        assert enforce_scanner_permissions()[1] == 401


def test_dispatch_still_requires_production_permission(app):
    with app.test_request_context('/scanner', method='POST', json={'type': 'Opakowanie', 'linia': 'AGRO'}):
        session.update(zalogowany=True, rola='pracownik', grupa='PSD')
        request.url_rule = Rule('/scanner', endpoint='scanner.dispatch')
        with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
                'app.core.scanner_permissions.get_db_connection') as db:
            assert enforce_scanner_permissions()[1] == 403
            db.assert_not_called()


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
def test_blueprint_shared_move_ignores_legacy_function_and_page_acl(app, kind):
    from app.blueprints.scanner.base import scanner_bp
    from app.core.function_permissions import register_function_permissions
    app.register_blueprint(scanner_bp)
    register_function_permissions(app)
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'linia': 'PSD'}
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='OSIP', login='scanner-test')
    with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
            'app.core.scanner_permissions.get_db_connection', return_value=conn), patch(
            'app.services.warehouse_v2_service.WarehouseV2Service.move_pallet', return_value=(True, 'OK', None)) as move:
        response = client.post('/agro/scanner/move', json={
            'type': kind, 'linia': 'AGRO', 'surowiec_id': 7, 'nr_palety': 'TEST7', 'lokalizacja': 'LP01'})
    assert response.status_code == 200
    assert response.json['success']
    move.assert_called_once()


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
def test_shared_move_cannot_bypass_production_guard(app, kind):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'linia': 'PSD'}
    with app.test_request_context('/scanner', method='POST', json={
            'type': kind, 'surowiec_id': 7, 'lokalizacja': 'BB20', 'linia': 'AGRO'}):
        session.update(zalogowany=True, rola='pracownik', grupa='PSD')
        request.url_rule = Rule('/scanner', endpoint='scanner.move')
        with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
                'app.core.scanner_permissions.get_db_connection', return_value=conn):
            assert enforce_scanner_permissions()[1] == 403


@pytest.mark.parametrize('kind', ['Surowiec', 'Opakowanie', 'Dodatek'])
def test_panel_function_override_cannot_block_shared_move(app, kind):
    from app.core.function_permissions import register_function_permissions
    from flask import jsonify
    app.add_url_rule('/api/pallet/move', endpoint='warehouse_v2.move_pallet',
                     view_func=lambda: jsonify(success=True), methods=['POST'])
    register_function_permissions(app)
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = {'id': 7, 'nr_palety': 'TEST7', 'linia': 'PSD'}
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='OSIP', user_id=123)
    with patch('app.core.warehouse_permissions._page_allowed', return_value=False), patch(
            'app.core.warehouse_permissions.get_db_connection', return_value=conn), patch(
            'app.core.contexts._get_role_permissions', return_value={
                'function.warehouse_v2.move_pallet': {'access': False}}):
        response = client.post('/api/pallet/move?sekcja=Magazyn&linia=PSD', json={
            'type': kind, 'id': 7, 'linia': 'AGRO', 'location': 'R01-01'})
    assert response.status_code == 200
    assert response.json['success']


@pytest.mark.parametrize('container', [
    {'is_shelf': True, 'inventory_key': 'POLKA'},
    {'is_station': True, 'is_production_station': False},
])
def test_shared_location_scan_filters_stock_individually(app, container):
    from app.blueprints.scanner.base import scanner_bp
    app.register_blueprint(scanner_bp)
    shared_item = {'id': 1, 'inventory_type': 'Opakowanie', 'nazwa': 'Etykiety', 'linia': 'PSD'}
    restricted_item = {'id': 2, 'inventory_type': 'Wyrób Gotowy', 'linia': 'PSD'}
    pallet = dict(container, items=[shared_item, restricted_item])
    client = app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='pracownik', grupa='AGRO')
    with patch('app.core.scanner_permissions._page_allowed', return_value=False), patch(
            'app.blueprints.scanner.base.ScannerService.lookup_by_location', return_value=pallet):
        response = client.post('/agro/scanner/lookup', json={'code': 'LP01', 'linia': 'AGRO'})
    assert response.status_code == 200
    assert response.json['pallet']['items'] == [shared_item]
