from unittest.mock import MagicMock, patch
import pytest

from app.services.magazyn_dostawy.location_service import LocationService
from app.services.scanner_service import ScannerService
from app.services.inwentaryzacja_service import InwentaryzacjaService


def test_location_service_recognizes_r09_locations():
    assert LocationService._is_rack_location_code('R090101') is True
    assert LocationService._is_rack_location_code('R090406') is True
    assert LocationService._is_rack_location_code('R090203') is True
    assert LocationService._is_rack_location_code('R010101') is True
    assert LocationService._is_rack_location_code('INVALID_CODE') is False


def test_location_service_generates_all_24_shelf_locations_for_r09():
    candidates = LocationService._build_static_location_candidates()
    assert 'R09' in candidates
    
    # 4 columns (01-04) x 6 rows (01-06) = 24 locations
    expected_count = 0
    for place in range(1, 5):
        for row in range(1, 7):
            loc_code = f"R09{place:02d}{row:02d}"
            assert loc_code in candidates
            expected_count += 1
            
    assert expected_count == 24


def test_scanner_lookup_returns_multi_item_shelf_for_r09():
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        # magazyn_surowce
        [{'id': 101, 'ilosc': 250.0, 'nazwa': 'Surowiec A', 'lokalizacja': 'R090101', 'nr_palety': 'SUR000001', 'nr_partii': 'P01', 'data_produkcji': None, 'data_przydatnosci': None}],
        # magazyn_opakowania
        [{'id': 202, 'ilosc': 50.0, 'nazwa': 'Worek 25kg', 'lokalizacja': 'R090101', 'nr_palety': 'OPK000002', 'nr_partii': 'P02', 'data_produkcji': None, 'data_przydatnosci': None}],
        # magazyn_dodatki
        [],
        # magazyn_palety
        [{'id': 303, 'ilosc': 800.0, 'nazwa': 'Wyrób C', 'lokalizacja': 'R090101', 'nr_palety': 'PAL000003', 'nr_partii': 'P03', 'data_produkcji': None, 'data_przydatnosci': None}],
    ]

    with patch('app.services.scanner_service.get_db_connection', return_value=mock_conn):
        result = ScannerService.lookup_by_location('R090101', linia='AGRO')

    assert result is not None
    assert result.get('is_shelf') is True
    assert result.get('lokalizacja') == 'R090101'
    items = result.get('items', [])
    assert len(items) == 3
    assert items[0]['nazwa'] == 'Surowiec A'
    assert items[1]['nazwa'] == 'Worek 25kg'
    assert items[2]['nazwa'] == 'Wyrób C'


def test_inwentaryzacja_service_normalize_r09_loc_key():
    assert InwentaryzacjaService.normalize_loc_key('r090101') == 'R090101'
    assert InwentaryzacjaService.normalize_loc_key('R-09-04-06') == 'R090406'
    assert InwentaryzacjaService.normalize_loc_key('090101') == 'R090101'


def test_check_rack_location_availability_allows_multiple_pallets_on_r09():
    from app.utils.location_validator import check_rack_location_availability
    is_valid, err = check_rack_location_availability('R090101', current_nr_palety='NEW_PALLET_01')
    assert is_valid is True
    assert err is None

    is_valid_r09_other, err_r09 = check_rack_location_availability('R090406')
    assert is_valid_r09_other is True
    assert err_r09 is None

