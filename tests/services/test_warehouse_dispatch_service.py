"""
Testy dla WarehouseDispatchService (Wydania Zewnętrzne na Samochód).
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.warehouse_dispatch_service import WarehouseDispatchService


def test_get_available_pallets():
    service = WarehouseDispatchService()
    mock_pallets = [
        {'id': 1, 'nr_palety': 'PAL-101', 'nazwa': 'Surowiec A', 'stan_magazynowy': 1000.0}
    ]
    service._repository.get_available_pallets = MagicMock(return_value=mock_pallets)

    res = service.get_available_pallets()
    assert len(res) == 1
    assert res[0]['nr_palety'] == 'PAL-101'


def test_dispatch_pallet_to_vehicle_missing_data():
    service = WarehouseDispatchService()

    success, msg = service.dispatch_pallet_to_vehicle({}, 'magazynier1')
    assert success is False
    assert "Wymagany jest numer palety" in msg

    success, msg = service.dispatch_pallet_to_vehicle({'nr_palety': 'PAL-101'}, 'magazynier1')
    assert success is False
    assert "Wymagana jest nazwa produktu" in msg


def test_dispatch_pallet_to_vehicle_success():
    service = WarehouseDispatchService()
    service._repository.create_dispatch = MagicMock(return_value=42)

    payload = {
        'nr_palety': 'PAL-101',
        'nazwa_produktu': 'Kwas Cytrynowy',
        'typ_palety': 'Surowiec',
        'ilosc_kg': 500,
        'nr_rejestracyjny': 'DW 12345',
        'kierowca': 'Jan Kowalski',
        'odbiorca': 'Klient ABC',
        'nr_dokumentu_wz': 'WZ/2026/001'
    }

    success, msg = service.dispatch_pallet_to_vehicle(payload, 'magazynier1')
    assert success is True
    assert "ID #42" in msg
    service._repository.create_dispatch.assert_called_once()
