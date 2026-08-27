from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.usefixtures("app")
class TestSuspendOrderFlow:
    @patch("app.services.planning.status.get_table_name", return_value="plan_produkcji_agro")
    @patch("app.services.planning.status.get_db_connection")
    def test_suspend_order_updates_status_to_zawieszone(
        self,
        mock_get_db_connection,
        _mock_get_table_name,
        client,
    ):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db_connection.return_value = mock_conn

        mock_cursor.fetchone.return_value = ("AGRO TEST PRODUCT",)

        with client.session_transaction() as sess:
            sess["zalogowany"] = True
            sess["login"] = "operator1"
            sess["rola"] = "admin"
            sess["selected_hall_view"] = "AGRO"

        response = client.post(
            "/zawies_zlecenie/123",
            data={
                "linia": "AGRO",
                "sekcja": "Workowanie",
                "data_planu": "2026-08-25",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        executed_sql = "\n".join(str(call.args[0]) for call in mock_cursor.execute.call_args_list if call.args)
        assert "SET status='zawieszone'" in executed_sql
