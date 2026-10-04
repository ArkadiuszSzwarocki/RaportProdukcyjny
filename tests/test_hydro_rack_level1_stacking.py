from unittest.mock import MagicMock, patch
import pytest

from app.utils.location_validator import is_rack_level_1, check_rack_location_availability


def test_is_rack_level_1_identifies_level_1_slots():
    assert is_rack_level_1('R010101') is True
    assert is_rack_level_1('R010102') is False
    assert is_rack_level_1('R020501') is True
    assert is_rack_level_1('R020503') is False
    assert is_rack_level_1('R-01-01-01') is True
    assert is_rack_level_1('r030201') is True
    assert is_rack_level_1('MS01') is False
    assert is_rack_level_1('BF_MS01') is False
    assert is_rack_level_1('') is False
    assert is_rack_level_1(None) is False


def test_hydro_stacking_on_level_1_empty_slot():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability('R010101', product_name='Hydro')
    assert is_valid is True
    assert err is None


def test_hydro_stacking_allows_second_hydro_pallet_on_level_1():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate 1 existing Hydro pallet in magazyn_surowce
    mock_cursor.fetchall.side_effect = [
        [{'nr_palety': 'SUR000001', 'product_name': 'Hydro'}],  # magazyn_surowce
        [],  # magazyn_agro_surowce
        [],  # magazyn_opakowania
        [],  # magazyn_agro_opakowania
        [],  # magazyn_dodatki
        [],  # magazyn_palety
        [],  # magazyn_palety_agro
    ]

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability(
            'R010101',
            current_nr_palety='SUR000002',
            product_name='Hydro'
        )
    assert is_valid is True
    assert err is None


def test_hydro_stacking_rejects_third_hydro_pallet_on_level_1():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Simulate 2 existing Hydro pallets in magazyn_surowce
    mock_cursor.fetchall.side_effect = [
        [
            {'nr_palety': 'SUR000001', 'product_name': 'Hydro'},
            {'nr_palety': 'SUR000002', 'product_name': 'Hydro'}
        ],  # magazyn_surowce
        [], [], [], [], [], []
    ]

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability(
            'R010101',
            current_nr_palety='SUR000003',
            product_name='Hydro'
        )
    assert is_valid is False
    assert "osiągnęła maksymalną pojemność (2 palety Hydro" in err


def test_level_1_rejects_second_pallet_if_not_hydro():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Slot has 1 Hydro pallet, but user tries to place Sugar
    mock_cursor.fetchall.side_effect = [
        [{'nr_palety': 'SUR000001', 'product_name': 'Hydro'}],
        [], [], [], [], [], []
    ]

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability(
            'R010101',
            current_nr_palety='SUR000099',
            product_name='Cukier'
        )
    assert is_valid is False
    assert "Piętrowanie na poziomie 1 dozwolone jest wyłącznie dla surowca Hydro" in err


def test_level_1_rejects_hydro_if_existing_pallet_is_not_hydro():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Slot has 1 Cukier pallet, user tries to place Hydro
    mock_cursor.fetchall.side_effect = [
        [{'nr_palety': 'SUR000055', 'product_name': 'Cukier'}],
        [], [], [], [], [], []
    ]

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability(
            'R010101',
            current_nr_palety='SUR000002',
            product_name='Hydro'
        )
    assert is_valid is False
    assert "Piętrowanie Hydro jest możliwe tylko na innej palecie Hydro" in err


def test_level_2_rejects_second_hydro_pallet():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    # Level 2 (R010102) has 1 Hydro pallet
    mock_cursor.fetchall.side_effect = [
        [{'nr_palety': 'SUR000001', 'product_name': 'Hydro'}],
        [], [], [], [], [], []
    ]

    with patch('app.core.database.get_db_connection', return_value=mock_conn):
        is_valid, err = check_rack_location_availability(
            'R010102',
            current_nr_palety='SUR000002',
            product_name='Hydro'
        )
    assert is_valid is False
    assert "Lokalizacja R010102 jest zajęta przez paletę SUR000001" in err


def test_acceptance_service_allows_second_hydro_pallet_on_level_1():
    from app.services.magazyn_dostawy.acceptance_service import AcceptanceService

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    # MySQL returns an integer identifier after INSERT.  A bare MagicMock
    # cannot be persisted in the delivery item's JSON metadata.
    mock_cursor.lastrowid = 42

    # Mock order fetching in accept_item
    import json
    order_items = [{
        'id': 10,
        'materialName': 'Hydro',
        'productName': 'Hydro',
        'unitsPerPallet': 1000,
        'packageForm': 'big_bag',
        'nr_palety': 'SUR_HYDRO_02'
    }]
    mock_cursor.fetchone.side_effect = [
        # SELECT id, type, items, status, linia FROM magazyn_dostawy WHERE id = %s
        {'id': 1, 'type': 'RAW_MATERIAL', 'status': 'OCZEKUJE', 'items': json.dumps(order_items), 'linia': 'PSD', 'supplier': 'Test', 'lokalizacja_z': 'DOSTAWA'},
        # exist check for nr_palety in magazyn_surowce
        None, None, None, None, None, None
    ]
    mock_cursor.fetchall.return_value = []

    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=mock_conn), \
         patch('app.utils.location_validator.check_rack_location_availability', return_value=(True, None)), \
         patch('app.utils.surowiec_validator.is_valid_surowiec', return_value=True), \
         patch('app.services.magazyn_dostawy.acceptance_service.MovementRecorder.record_movement', return_value=True):
        ok, msg, extra = AcceptanceService.accept_item(
            dostawa_id=1,
            item_id=10,
            lokalizacja='R010101',
            login='admin'
        )
    assert ok is True, msg


def test_dostawa_fallback_redirect(authenticated_client):
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchone.return_value = {
        'id': '563d2bcb-955e-4d51-b007-665aa35a9d60',
        'status': 'OCZEKUJE',
        'supplier': '',
        'lokalizacja_z': 'MP01'
    }

    with patch('app.blueprints.magazyn_dostawy.routes.transfer.get_db_connection', return_value=mock_conn):
        res = authenticated_client.get('/magazyn-dostawy/563d2bcb-955e-4d51-b007-665aa35a9d60?linia=ALL')
    
    assert res.status_code == 302
    assert '/magazyn-dostawy/przyjecie-ruchu/563d2bcb-955e-4d51-b007-665aa35a9d60' in res.headers['Location']

