from unittest.mock import MagicMock, patch

from app.services.picking_service import PickingService


def _mock_lock_connection(acquired=True):
    cursor = MagicMock()
    cursor.fetchone.return_value = (1 if acquired else 0,)
    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection, cursor


def _start_picking_with_fresh_calculation(service, request_data, fresh_calculation):
    lock_connection, _ = _mock_lock_connection(acquired=True)
    calculator = MagicMock()
    calculator.calculate_and_check_stock.return_value = (
        True,
        'Zapotrzebowanie przeliczone.',
        fresh_calculation,
    )

    with patch('app.services.picking_service.get_db_connection', return_value=lock_connection), \
         patch('app.services.picking_service.WarehouseOrderService', return_value=calculator), \
         patch.object(service, '_check_pending_deliveries', return_value=[]), \
         patch('app.services.picking_service.validate_surowiec_name', return_value=(True, '')):
        result = service.start_picking(request_data, 'testUser')

    return result, calculator


def test_start_picking_rechecks_stock_and_orders_only_missing_items():
    service = PickingService()
    service._picking_repo = MagicMock()
    service._picking_repo.get_next_order_sequence.return_value = 99
    service._picking_repo.create_picking_items.return_value = 4

    service._order_repo = MagicMock()
    service._order_repo.create.return_value = 123

    request_data = {
        'order_tons': 3.0,
        'linia': 'AGRO',
        'items': [
            {'surowiec_nazwa': 'Makuch Lniany', 'przelicznik_na_1t': 285.0},
            {'surowiec_nazwa': 'BM2 do Lnu', 'przelicznik_na_1t': 180.0},
            {'surowiec_nazwa': 'Mąka pszenna', 'przelicznik_na_1t': 220.0},
        ],
    }

    fresh_calculation = {
        'order_tons': 3.0,
        'items': [
            {
                'surowiec_nazwa': 'Makuch Lniany',
                'potrzebne_kg': 855.0,
                'palety_fifo': [
                    {'id': 101, 'nr_palety': 'P1', 'lokalizacja': 'R010101', 'stan_magazynowy': 886.0, 'is_blocked': False}
                ],
                'zablokowane_kg': 0.0,
            },
            {
                'surowiec_nazwa': 'BM2 do Lnu',
                'potrzebne_kg': 540.0,
                'palety_fifo': [],
                'zablokowane_kg': 0.0,
            },
            {
                'surowiec_nazwa': 'Mąka pszenna',
                'potrzebne_kg': 660.0,
                'palety_fifo': [
                    {'id': 102, 'nr_palety': 'P2', 'lokalizacja': 'R020101', 'stan_magazynowy': 1000.0, 'is_blocked': False}
                ],
                'zablokowane_kg': 0.0,
            },
        ],
    }

    (success, message, payload), calculator = _start_picking_with_fresh_calculation(
        service,
        request_data,
        fresh_calculation,
    )

    assert success is True
    assert payload['order_id'] == 123
    assert payload['total_missing_surowce'] == 1
    calculator.calculate_and_check_stock.assert_called_once_with(
        request_data['items'],
        3.0,
        'AGRO',
    )

    service._order_repo.create.assert_called_once()
    ordered_items = service._order_repo.create.call_args.kwargs['items']
    assert len(ordered_items) == 1
    assert ordered_items[0]['surowiec_nazwa'] == 'BM2 do Lnu'
    assert ordered_items[0]['ilosc_kg'] == 540.0
    assert ordered_items[0]['brakujace_kg'] == 540.0

    # Brak jest utrzymany jako placeholder, aby późniejszy PZ/MM mógł go uzupełnić.
    picking_rows = service._picking_repo.create_picking_items.call_args.args[0]
    placeholder = next(row for row in picking_rows if row['paleta_id'] == 0)
    assert placeholder['surowiec_nazwa'] == 'BM2 do Lnu'
    assert placeholder['ilosc_kg'] == 540.0
    assert placeholder['status'] == 'POMINIETA'
    assert 'brakujące' in message.lower()


def test_start_picking_partial_shortage_creates_placeholder_and_skips_blocked_pallets():
    service = PickingService()
    service._picking_repo = MagicMock()
    service._picking_repo.get_next_order_sequence.return_value = 7
    service._picking_repo.create_picking_items.return_value = 2

    service._order_repo = MagicMock()
    service._order_repo.create.return_value = 321

    request_data = {
        'order_tons': 1.0,
        'items': [
            {'surowiec_nazwa': 'Surowiec A', 'przelicznik_na_1t': 1000.0},
        ],
    }
    fresh_calculation = {
        'order_tons': 1.0,
        'items': [
            {
                'surowiec_nazwa': 'Surowiec A',
                'potrzebne_kg': 1000.0,
                'zablokowane_kg': 300.0,
                'palety_fifo': [
                    {'id': 10, 'nr_palety': 'A1', 'lokalizacja': 'R010101', 'stan_magazynowy': 600.0, 'is_blocked': False, 'fifo_rank': 1},
                    {'id': 11, 'nr_palety': 'A2', 'lokalizacja': 'R010102', 'stan_magazynowy': 300.0, 'is_blocked': True, 'powod_blokady': 'JAKOŚĆ'},
                ],
            }
        ],
    }

    (success, _, payload), _ = _start_picking_with_fresh_calculation(
        service,
        request_data,
        fresh_calculation,
    )

    assert success is True
    assert payload['total_missing_surowce'] == 1

    rows = service._picking_repo.create_picking_items.call_args.args[0]
    assert len(rows) == 2
    assert [row['paleta_id'] for row in rows] == [10, 0]
    assert all(row['paleta_id'] != 11 for row in rows)

    placeholder = rows[1]
    assert placeholder['ilosc_kg'] == 400.0
    assert placeholder['status'] == 'POMINIETA'

    order_items = service._order_repo.create.call_args.kwargs['items']
    assert order_items[0]['ilosc_kg'] == 400.0
    assert payload['summary'][0]['zablokowane_kg'] == 300.0


def test_start_picking_no_order_created_when_all_in_stock():
    service = PickingService()
    service._picking_repo = MagicMock()
    service._picking_repo.get_next_order_sequence.return_value = 100
    service._picking_repo.create_picking_items.return_value = 1
    service._order_repo = MagicMock()

    request_data = {
        'order_tons': 1.0,
        'items': [
            {'surowiec_nazwa': 'Makuch Lniany', 'przelicznik_na_1t': 500.0},
        ],
    }
    fresh_calculation = {
        'order_tons': 1.0,
        'items': [
            {
                'surowiec_nazwa': 'Makuch Lniany',
                'potrzebne_kg': 500.0,
                'zablokowane_kg': 0.0,
                'palety_fifo': [
                    {'id': 201, 'nr_palety': 'P3', 'lokalizacja': 'R010101', 'stan_magazynowy': 600.0, 'is_blocked': False}
                ],
            }
        ],
    }

    (success, message, payload), _ = _start_picking_with_fresh_calculation(
        service,
        request_data,
        fresh_calculation,
    )

    assert success is True
    assert payload['order_id'] is None
    assert payload['total_missing_surowce'] == 0
    service._order_repo.create.assert_not_called()
    assert 'Wszystkie surowce są pokryte' in message


def test_start_picking_stops_when_advisory_lock_is_busy():
    service = PickingService()
    lock_connection, _ = _mock_lock_connection(acquired=False)

    with patch('app.services.picking_service.get_db_connection', return_value=lock_connection):
        success, message, payload = service.start_picking(
            {
                'order_tons': 1.0,
                'items': [{'surowiec_nazwa': 'A', 'przelicznik_na_1t': 10.0}],
            },
            'testUser',
        )

    assert success is False
    assert payload == {}
    assert 'rezerwowany' in message


def test_move_pallet_to_mp01_returns_false_when_current_state_changed():
    service = PickingService()
    cursor = MagicMock()
    cursor.rowcount = 0
    connection = MagicMock()
    connection.cursor.return_value = cursor

    with patch('app.services.picking_service.get_db_connection', return_value=connection):
        result = service._move_pallet_to_mp01(55, 'R010101', 'magazynier')

    assert result is False
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_warehouse_order_service_cleans_non_missing_items():
    from app.services.warehouse_order_service import WarehouseOrderService

    service = WarehouseOrderService()
    raw_items = [
        {'surowiec_nazwa': 'BM2', 'ilosc_kg': 750.0, 'brakujace_kg': 750.0},
        {'surowiec_nazwa': 'SWP Serwatka', 'ilosc_kg': 480.0, 'brakujace_kg': 0.0},
        {'surowiec_nazwa': 'IFFMP', 'ilosc_kg': 150.0, 'brakujace_kg': 150.0},
        {'surowiec_nazwa': 'Hydro', 'ilosc_kg': 294.0, 'brakujace_kg': 0.0},
    ]

    cleaned = service._clean_order_items(raw_items)
    assert len(cleaned) == 2
    assert cleaned[0]['surowiec_nazwa'] == 'BM2'
    assert cleaned[0]['ilosc_kg'] == 750.0
    assert cleaned[1]['surowiec_nazwa'] == 'IFFMP'
    assert cleaned[1]['ilosc_kg'] == 150.0
