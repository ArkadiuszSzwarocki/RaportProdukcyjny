from datetime import date
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.usefixtures("app")
class TestStartWorkowanieChecklist:
    @patch("app.blueprints.routes_production_orders.get_table_name", return_value="plan_produkcji_agro")
    @patch("app.blueprints.routes_production_orders.get_db_connection")
    def test_start_agro_workowanie_requires_operator_checklist(self, mock_get_db_connection, _mock_get_table_name, client):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db_connection.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            ("AGRO TEST", 1200, "Workowanie", date(2026, 5, 20), "AGRO", "zaplanowane", 0, 7, 3),
            None,
        ]

        with client.session_transaction() as sess:
            sess["zalogowany"] = True
            sess["login"] = "operator1"
            sess["rola"] = "admin"
            sess["selected_hall_view"] = "AGRO"

        response = client.post(
            "/start_zlecenie/123",
            data={"linia": "AGRO", "sekcja": "Workowanie"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("checklist" in str(message).lower() for _category, message in flashes)

        executed_sql = "\n".join(str(call.args[0]) for call in mock_cursor.execute.call_args_list if call.args)
        assert "SET status='w toku'" not in executed_sql

    @patch("app.blueprints.routes_production_orders.audit_log")
    @patch("app.blueprints.routes_production_orders.check_password_hash", return_value=True)
    @patch("app.blueprints.routes_production_orders.get_table_name", return_value="plan_produkcji_agro")
    @patch("app.blueprints.routes_production_orders.get_db_connection")
    def test_start_agro_workowanie_accepts_quality_second_signature(
        self,
        mock_get_db_connection,
        _mock_get_table_name,
        _mock_check_password_hash,
        mock_audit_log,
        client,
    ):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db_connection.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            ("AGRO TEST", 1200, "Workowanie", date(2026, 5, 20), "AGRO", "zaplanowane", 0, 7, 3),
            None,
            ("pbkdf2:sha256:test", "lider"),
        ]

        with client.session_transaction() as sess:
            sess["zalogowany"] = True
            sess["login"] = "operator1"
            sess["rola"] = "admin"
            sess["selected_hall_view"] = "AGRO"

        response = client.post(
            "/start_zlecenie/123",
            data={
                "linia": "AGRO",
                "sekcja": "Workowanie",
                "start_checklist_confirmed": "1",
                "quality_login": "qc.user",
                "quality_password": "secret",
                "data_produkcji": "2026-05-21",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        executed_sql = "\n".join(str(call.args[0]) for call in mock_cursor.execute.call_args_list if call.args)
        assert "SET status='w toku'" in executed_sql
        assert "start_checklist_operator_login" in executed_sql
        assert "start_checklist_quality_login" in executed_sql
        assert "data_produkcji" in executed_sql

        assert mock_audit_log.called
        audit_details = mock_audit_log.call_args[0][1]
        assert "quality=qc.user" in audit_details
        assert "checklist=OK" in audit_details

    @patch("app.blueprints.routes_production_orders.check_password_hash", return_value=True)
    @patch("app.blueprints.routes_production_orders.get_table_name", return_value="plan_produkcji_agro")
    @patch("app.blueprints.routes_production_orders.get_db_connection")
    def test_start_agro_workowanie_rejects_unauthorized_second_signature_role(
        self,
        mock_get_db_connection,
        _mock_get_table_name,
        _mock_check_password_hash,
        client,
    ):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_db_connection.return_value = mock_conn

        mock_cursor.fetchone.side_effect = [
            ("AGRO TEST", 1200, "Workowanie", date(2026, 5, 20), "AGRO", "zaplanowane", 0, 7, 3),
            None,
            ("pbkdf2:sha256:test", "laborant"),
        ]

        with client.session_transaction() as sess:
            sess["zalogowany"] = True
            sess["login"] = "operator1"
            sess["rola"] = "admin"
            sess["selected_hall_view"] = "AGRO"

        response = client.post(
            "/start_zlecenie/123",
            data={
                "linia": "AGRO",
                "sekcja": "Workowanie",
                "start_checklist_confirmed": "1",
                "quality_login": "qc.user",
                "quality_password": "secret",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any("nie ma uprawnień" in str(message).lower() for _category, message in flashes)

        executed_sql = "\n".join(str(call.args[0]) for call in mock_cursor.execute.call_args_list if call.args)
        assert "SET status='w toku'" not in executed_sql
