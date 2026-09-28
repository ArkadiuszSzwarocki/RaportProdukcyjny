from unittest.mock import MagicMock, patch
from app.services.picking_service import PickingService


def test_start_picking_orders_only_missing_items():
    service = PickingService()

    # Mock picking_repo and order_repo
    service._picking_repo = MagicMock()
    service._picking_repo.get_next_order_sequence.return_value = 99
    service._picking_repo.create_picking_items.return_value = 2

    service._order_repo = MagicMock()
    service._order_repo.create.return_value = 123

    # Calculation results: 3 items
    # 1: Makuch Lniany (needed 855 kg, allocated 886 kg, missing 0 kg)
    # 2: BM2 do Lnu (needed 540 kg, allocated 0 kg, missing 540 kg)
    # 3: Mąka pszenna (needed 660 kg, allocated 1000 kg, missing 0 kg)
    calculation_results = {
        'order_tons': 3.0,
        'items': [
            {
                'surowiec_nazwa': 'Makuch Lniany',
                'potrzebne_kg': 855.0,
                'palety_fifo': [
                    {'id': 101, 'nr_palety': 'P1', 'lokalizacja': 'R010101', 'stan_magazynowy': 886.0, 'is_blocked': False}
                ]
            },
            {
                'surowiec_nazwa': 'BM2 do Lnu',
                'potrzebne_kg': 540.0,
                'palety_fifo': []  # No pallets available -> missing 540 kg
            },
            {
                'surowiec_nazwa': 'Mąka pszenna',
                'potrzebne_kg': 660.0,
                'palety_fifo': [
                    {'id': 102, 'nr_palety': 'P2', 'lokalizacja': 'R020101', 'stan_magazynowy': 1000.0, 'is_blocked': False}
                ]
            }
        ]
    }

    with patch.object(service, '_check_pending_deliveries', return_value=[]), \
         patch('app.services.picking_service.validate_surowiec_name', return_value=(True, None)):
        success, message, payload = service.start_picking(calculation_results, 'testUser')

    assert success is True
    assert payload['order_id'] == 123
    assert payload['total_missing_surowce'] == 1

    # Verify order_repo.create was called ONCE, and ONLY with the missing item (BM2 do Lnu)
    service._order_repo.create.assert_called_once()
    call_args = service._order_repo.create.call_args[1]
    items = call_args['items']
    assert len(items) == 1
    assert items[0]['surowiec_nazwa'] == 'BM2 do Lnu'
    assert items[0]['ilosc_kg'] == 540.0
    assert items[0]['brakujace_kg'] == 540.0


def test_start_picking_no_order_created_when_all_in_stock():
    service = PickingService()

    service._picking_repo = MagicMock()
    service._picking_repo.get_next_order_sequence.return_value = 100
    service._picking_repo.create_picking_items.return_value = 1

    service._order_repo = MagicMock()

    calculation_results = {
        'order_tons': 1.0,
        'items': [
            {
                'surowiec_nazwa': 'Makuch Lniany',
                'potrzebne_kg': 500.0,
                'palety_fifo': [
                    {'id': 201, 'nr_palety': 'P3', 'lokalizacja': 'R010101', 'stan_magazynowy': 600.0, 'is_blocked': False}
                ]
            }
        ]
    }

    with patch.object(service, '_check_pending_deliveries', return_value=[]), \
         patch('app.services.picking_service.validate_surowiec_name', return_value=(True, None)):
        success, message, payload = service.start_picking(calculation_results, 'testUser')

    assert success is True
    assert payload['order_id'] is None
    assert payload['total_missing_surowce'] == 0

    # Ensure no warehouse order was created
    service._order_repo.create.assert_not_called()
    assert "Wszystkie surowce są na stanie magazynu" in message


def test_warehouse_order_service_cleans_non_missing_items():
    from app.services.warehouse_order_service import WarehouseOrderService
    service = WarehouseOrderService()

    raw_items = [
        {'surowiec_nazwa': 'BM2', 'ilosc_kg': 750.0, 'brakujace_kg': 750.0},
        {'surowiec_nazwa': 'SWP Serwatka', 'ilosc_kg': 480.0, 'brakujace_kg': 0.0},
        {'surowiec_nazwa': 'IFFMP', 'ilosc_kg': 150.0, 'brakujace_kg': 150.0},
        {'surowiec_nazwa': 'Hydro', 'ilosc_kg': 294.0, 'brakujace_kg': 0.0}
    ]

    cleaned = service._clean_order_items(raw_items)
    assert len(cleaned) == 2
    assert cleaned[0]['surowiec_nazwa'] == 'BM2'
    assert cleaned[0]['ilosc_kg'] == 750.0
    assert cleaned[1]['surowiec_nazwa'] == 'IFFMP'
    assert cleaned[1]['ilosc_kg'] == 150.0

