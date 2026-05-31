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


def test_normalize_scanned_code_extracts_gs1_ai00_sscc():
    raw = 'https://scan.local/label?code=(00)590123412345678901&src=zebra'
    normalized = ScannerService._normalize_scanned_code(raw)
    assert normalized == '590123412345678901'


def test_lookup_prefixed_opk_uses_prefix_not_first_numeric_match():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def _fake_inventory_lookup(
        _cur,
        base_table,
        _linia,
        *,
        qty_col,
        name_col='nazwa',
        location_code=None,
        item_id=None,
        pallet_no=None,
    ):
        if item_id != 12:
            return None
        if base_table == 'magazyn_surowce':
            return {'id': 12, 'nazwa': 'Surowiec 12', 'ilosc': 400, 'lokalizacja': 'MS01'}
        if base_table == 'magazyn_opakowania':
            return {'id': 12, 'nazwa': 'Worek 25kg', 'ilosc': 900, 'lokalizacja': 'MOP01'}
        return None

    with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn), patch(
        'app.services.scanner_service.ScannerService._lookup_inventory_row', side_effect=_fake_inventory_lookup
    ), patch(
        'app.services.scanner_service.ScannerService._lookup_finished_goods', return_value=None
    ):
        result = ScannerService.lookup_by_location('OPK-12', linia='AGRO')

    assert result is not None
    assert result['inventory_type'] == 'Opakowanie'
    assert result['inventory_code'] == 'OPK-12'
    assert result['nazwa'] == 'Worek 25kg'


def test_lookup_finds_finished_goods_by_non_sscc_pallet_number():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    def _fake_finished_goods_lookup(
        _cur,
        _linia,
        *,
        item_id=None,
        location_code=None,
        pallet_no=None,
    ):
        if pallet_no == 'WGX-2026-0001':
            return {'id': 77, 'nazwa': 'Granulat WG', 'ilosc': 1234.0, 'lokalizacja': 'MGW01'}
        return None

    with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn), patch(
        'app.services.scanner_service.ScannerService._lookup_inventory_row', return_value=None
    ), patch(
        'app.services.scanner_service.ScannerService._lookup_finished_goods', side_effect=_fake_finished_goods_lookup
    ):
        result = ScannerService.lookup_by_location('WGX-2026-0001', linia='AGRO')

    assert result is not None
    assert result['inventory_type'] == 'Wyrób Gotowy'
    assert result['inventory_code'] == 'PAL-77'
