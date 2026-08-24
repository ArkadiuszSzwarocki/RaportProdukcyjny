"""
Testy dla WarehouseDispatchService (Wydania Zewnętrzne na Samochód).
"""
import pytest
from unittest.mock import MagicMock, patch
from app.services.warehouse_dispatch_service import WarehouseDispatchService


def test_lookup_pallet_for_dispatch_empty_code():
    service = WarehouseDispatchService()
    res = service.lookup_pallet_for_dispatch("")
    assert res is None


def test_lookup_pallet_for_dispatch_not_found():
    repo = MagicMock()
    repo.find_pallet_by_code.return_value = None
    service = WarehouseDispatchService(repository=repo)

    res = service.lookup_pallet_for_dispatch("PAL-999")
    assert res is None
    repo.find_pallet_by_code.assert_called_once()


def test_lookup_pallet_for_dispatch_success():
    repo = MagicMock()
    repo.find_pallet_by_code.return_value = {
        'id': 15,
        'nr_palety': 'PAL-101',
        'nazwa': 'Siarczan Magnezu',
        'stan_magazynowy': 850.5,
        'lokalizacja': 'R020101',
        'nr_partii': 'LOT-2026-A',
        'typ': 'Surowiec',
        'linia': 'AGRO'
    }
    service = WarehouseDispatchService(repository=repo)

    res = service.lookup_pallet_for_dispatch("PAL-101", preferred_line="AGRO")
    assert res is not None
    assert res['id'] == 15
    assert res['nr_palety'] == 'PAL-101'
    assert res['productName'] == 'Siarczan Magnezu'
    assert res['amount'] == 850.5
    assert res['location'] == 'R020101'
    assert res['batch'] == 'LOT-2026-A'


def test_dispatch_pallet_to_vehicle_missing_data():
    service = WarehouseDispatchService()

    success, msg = service.dispatch_pallet_to_vehicle({}, 'magazynier1')
    assert success is False
    assert "Wymagany jest numer palety" in msg

    success, msg = service.dispatch_pallet_to_vehicle({'nr_palety': 'PAL-101'}, 'magazynier1')
    assert success is False
    assert "Wymagana jest nazwa produktu" in msg


def test_dispatch_pallet_to_vehicle_success_with_stock_deduct():
    repo = MagicMock()
    repo.create_dispatch.return_value = 42
    repo.deduct_pallet_stock.return_value = True
    service = WarehouseDispatchService(repository=repo)

    payload = {
        'nr_palety': 'PAL-101',
        'pallet_id': 15,
        'nazwa_produktu': 'Kwas Cytrynowy',
        'typ_palety': 'Surowiec',
        'linia': 'AGRO',
        'ilosc_kg': 500.0,
        'nr_rejestracyjny': 'DW 12345',
        'kierowca': 'Jan Kowalski',
        'odbiorca': 'Klient ABC',
        'nr_dokumentu_wz': 'WZ/2026/001',
        'uwagi': 'Brak uwag'
    }

    success, msg = service.dispatch_pallet_to_vehicle(payload, 'magazynier1')
    assert success is True
    assert "ID #42" in msg
    repo.create_dispatch.assert_called_once()
    repo.deduct_pallet_stock.assert_called_once_with(
        pallet_id=15,
        typ_palety='Surowiec',
        linia='AGRO',
        ilosc_kg=500.0,
        src_table=None
    )


def test_get_dispatches_history_with_tuples():
    repo = MagicMock()
    # Tuples: id, nr_palety, nazwa_produktu, typ_palety, ilosc_kg, nr_rejestracyjny, kierowca, odbiorca, nr_dokumentu_wz, uwagi, magazynier, created_at
    repo.get_recent_dispatches.return_value = [
        (1, 'PAL-001', 'Kwas', 'Surowiec', 500.0, 'DW 12345', 'Kierowca A', 'Klient B', 'WZ-1', 'Uwagi', 'magazynier', None)
    ]
    service = WarehouseDispatchService(repository=repo)

    history = service.get_dispatches_history(limit=10)
    assert len(history) == 1
    assert history[0]['id'] == 1
    assert history[0]['nr_palety'] == 'PAL-001'
    assert history[0]['nazwa_produktu'] == 'Kwas'


def test_get_dispatches_history_with_dicts():
    repo = MagicMock()
    repo.get_recent_dispatches.return_value = [
        {'id': 2, 'nr_palety': 'PAL-002', 'nazwa_produktu': 'Soda', 'ilosc_kg': 250.0, 'created_at': None}
    ]
    service = WarehouseDispatchService(repository=repo)

    history = service.get_dispatches_history(limit=10)
    assert len(history) == 1
    assert history[0]['id'] == 2
    assert history[0]['nr_palety'] == 'PAL-002'


def test_dispatch_pallets_batch_to_vehicle():
    repo = MagicMock()
    repo.create_dispatch.side_effect = [101, 102]
    repo.deduct_pallet_stock.return_value = True
    service = WarehouseDispatchService(repository=repo)

    payload = {
        'nr_rejestracyjny': 'DW 12345',
        'kierowca': 'Jan Kowalski',
        'pallets': [
            {'pallet_id': 1, 'nr_palety': 'PAL-01', 'nazwa_produktu': 'P1', 'typ_palety': 'Wyrób Gotowy', 'linia': 'PSD', 'ilosc_kg': 1000.0},
            {'pallet_id': 2, 'nr_palety': 'PAL-02', 'nazwa_produktu': 'P2', 'typ_palety': 'Surowiec', 'linia': 'AGRO', 'ilosc_kg': 500.0}
        ]
    }

    success, msg = service.dispatch_pallet_to_vehicle(payload, 'magazynier1')
    assert success is True
    assert "Zarejestrowano załadunek 2 palet" in msg
    assert repo.create_dispatch.call_count == 2
    assert repo.deduct_pallet_stock.call_count == 2


def test_group_dispatches_by_wz():
    service = WarehouseDispatchService()
    raw = [
        {'id': 1, 'nr_dokumentu_wz': 'WZ/2026/01', 'nr_palety': 'P1', 'nazwa_produktu': 'Kwas', 'ilosc_kg': 1000.0, 'nr_rejestracyjny': 'DW 11', 'kierowca': 'A', 'odbiorca': 'Klient 1', 'created_at': '2026-08-24 10:00:00'},
        {'id': 2, 'nr_dokumentu_wz': 'WZ/2026/01', 'nr_palety': 'P2', 'nazwa_produktu': 'Soda', 'ilosc_kg': 500.0, 'nr_rejestracyjny': 'DW 11', 'kierowca': 'A', 'odbiorca': 'Klient 1', 'created_at': '2026-08-24 10:05:00'},
        {'id': 3, 'nr_dokumentu_wz': 'WZ/2026/02', 'nr_palety': 'P3', 'nazwa_produktu': 'Wapno', 'ilosc_kg': 750.0, 'nr_rejestracyjny': 'PO 22', 'kierowca': 'B', 'odbiorca': 'Klient 2', 'created_at': '2026-08-24 11:00:00'}
    ]

    grouped = service.group_dispatches_by_wz(raw)
    assert len(grouped) == 2
    wz1 = next(g for g in grouped if g['nr_dokumentu_wz'] == 'WZ/2026/01')
    assert wz1['pallets_count'] == 2
    assert wz1['total_weight_kg'] == 1500.0
    assert len(wz1['items']) == 2

    wz2 = next(g for g in grouped if g['nr_dokumentu_wz'] == 'WZ/2026/02')
    assert wz2['pallets_count'] == 1
    assert wz2['total_weight_kg'] == 750.0



