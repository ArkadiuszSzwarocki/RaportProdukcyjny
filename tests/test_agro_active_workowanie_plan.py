from datetime import date
from unittest.mock import MagicMock, patch

from app.services.agro_warehouse_service import AgroWarehouseService


def _mock_connection_with_cursor(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_get_active_workowanie_plan_falls_back_when_today_has_no_row():
    cursor = MagicMock()
    fallback_plan = {
        'id': 158,
        'produkt': 'KREMOWKA LEN',
        'data_planu': date(2026, 5, 29),
    }
    cursor.fetchone.side_effect = [None, fallback_plan]
    conn = _mock_connection_with_cursor(cursor)

    with patch('app.services.agro_warehouse_service.get_db_connection', return_value=conn), patch(
        'app.services.agro_warehouse_service.get_table_name', return_value='plan_produkcji_agro'
    ):
        result = AgroWarehouseService.get_active_workowanie_plan(linia='AGRO')

    assert result == fallback_plan
    assert cursor.execute.call_count == 2

    first_query = cursor.execute.call_args_list[0].args[0]
    second_query = cursor.execute.call_args_list[1].args[0]
    assert "DATE(data_planu) = CURDATE()" in first_query
    assert "DATE(data_planu) = CURDATE()" not in second_query
    conn.close.assert_called_once()


def test_get_active_workowanie_plan_with_target_date_skips_fallback():
    cursor = MagicMock()
    target_date = date(2026, 6, 1)
    expected_plan = {
        'id': 165,
        'produkt': 'KREMOWKA LEN',
        'data_planu': target_date,
    }
    cursor.fetchone.return_value = expected_plan
    conn = _mock_connection_with_cursor(cursor)

    with patch('app.services.agro_warehouse_service.get_db_connection', return_value=conn), patch(
        'app.services.agro_warehouse_service.get_table_name', return_value='plan_produkcji_agro'
    ):
        result = AgroWarehouseService.get_active_workowanie_plan(linia='AGRO', target_date=target_date)

    assert result == expected_plan
    assert cursor.execute.call_count == 1

    execute_args = cursor.execute.call_args.args
    assert "DATE(data_planu) = %s" in execute_args[0]
    assert execute_args[1] == (target_date,)
    conn.close.assert_called_once()
