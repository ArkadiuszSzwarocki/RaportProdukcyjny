"""Shared stock requires independent source and production permissions."""
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask, jsonify, session

from app.core.scanner_permissions import enforce_scanner_permissions


@pytest.mark.parametrize('role', ['lider', 'masteradmin'])
@pytest.mark.parametrize('source_allowed,target_allowed,expected', [
    (True, True, 200), (False, True, 403), (True, False, 403),
])
def test_shared_stock_dispatch_checks_physical_warehouse_and_destination(role, source_allowed, target_allowed, expected):
    app = Flask(__name__)
    app.secret_key = 'isolated-test-key'
    app.add_url_rule('/agro/scanner/dispatch', endpoint='scanner.dispatch', view_func=lambda: None, methods=['POST'])
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = {
        'id': 123, 'nr_palety': 'TEST-123', 'linia': 'AGRO', 'lokalizacja': 'MS01',
    }
    checks = []

    def allowed(line, section, write=True):
        checks.append((line, section, write))
        return target_allowed if (line, section) == ('AGRO', 'zasyp') else source_allowed

    with app.test_request_context('/agro/scanner/dispatch', method='POST', json={
        'surowiec_id': 123, 'nr_palety': 'TEST-123', 'linia': 'AGRO',
        'type': 'Surowiec', 'zbiornik': 'BB20',
    }):
        session.update(rola=role, zalogowany=True)
        with patch('app.core.scanner_permissions.get_db_connection', return_value=connection), patch(
                'app.core.scanner_permissions._page_allowed', side_effect=allowed), patch(
                'app.core.shared_raw_stock_permissions._page_allowed', side_effect=allowed):
            result = enforce_scanner_permissions()
        response = app.make_response(result if result is not None else jsonify(success=True))
        assert response.status_code == expected
        assert ('AGRO', 'zasyp', True) in checks
        if target_allowed:
            assert ('PSD', 'magazyn', True) in checks


def test_dispatch_rejects_conflicting_pallet_types_before_reading_stock():
    app = Flask(__name__)
    app.add_url_rule('/dispatch', endpoint='scanner.dispatch', view_func=lambda: None, methods=['POST'])
    with app.test_request_context('/dispatch', method='POST', json={
        'surowiec_id': 123, 'linia': 'AGRO', 'type': 'Dodatek', 'pallet_type': 'Surowiec',
    }), patch('app.core.scanner_permissions._page_allowed', return_value=True), patch(
            'app.core.scanner_permissions.get_db_connection') as connect:
        response, status = enforce_scanner_permissions()
        assert status == 400
        assert response.json['error'] == 'pallet_type_mismatch'
        connect.return_value.cursor.return_value.execute.assert_not_called()
