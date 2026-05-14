from unittest.mock import MagicMock, patch

from app.services.scanner_service import ScannerService


def _fake_table_name(base_table, _linia):
    return base_table


def test_lookup_returns_finished_goods_for_pal_prefix():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = {
        'id': 5,
        'nazwa': 'Granulat Test',
        'ilosc': 820.5,
        'lokalizacja': 'MGW01',
    }

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn), patch(
        'app.services.scanner_service.get_table_name', side_effect=_fake_table_name
    ):
        result = ScannerService.lookup_by_location('https://label.local/?code=PAL-5|MGW01', linia='AGRO')

    assert result is not None
    assert result['id'] == 5
    assert result['inventory_type'] == 'Wyrób Gotowy'
    assert result['inventory_code'] == 'PAL-5'
    assert result['can_dispatch'] is False
    assert result['can_split'] is False


def test_lookup_returns_packaging_for_location():
    mock_cursor = MagicMock()
    # 1) brak w surowcach, 2) znalezione w opakowaniach
    mock_cursor.fetchone.side_effect = [
        None,
        {
            'id': 12,
            'nazwa': 'Worek 25kg',
            'ilosc': 1400,
            'lokalizacja': 'MOP01',
        },
    ]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn), patch(
        'app.services.scanner_service.get_table_name', side_effect=_fake_table_name
    ):
        result = ScannerService.lookup_by_location('mop01', linia='AGRO')

    assert result is not None
    assert result['inventory_type'] == 'Opakowanie'
    assert result['inventory_code'] == 'OPK-12'
    assert result['lokalizacja'] == 'MOP01'
    assert result['can_dispatch'] is False


def test_lookup_route_returns_inventory_payload(client):
    payload = {
        'id': 7,
        'nazwa': 'Test item',
        'stan_magazynowy': 300.0,
        'lokalizacja': 'MGW01',
        'inventory_type': 'Wyrób Gotowy',
        'inventory_code': 'PAL-7',
        'can_dispatch': False,
        'can_split': False,
        'can_print_label': False,
        'unit': 'kg',
    }

    with patch('app.blueprints.routes_scanner.ScannerService.lookup_by_location', return_value=payload):
        response = client.post('/agro/scanner/lookup', json={'code': 'PAL-7', 'linia': 'AGRO'})

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['pallet']['inventory_code'] == 'PAL-7'
