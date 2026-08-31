import pytest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from app.services.auto_report_service import AutoReportService


class TestAutoReportServiceWeekdayAndConfig:
    """Testy weryfikujące poprawność konfiguracji dni i linii dla auto-raportów."""

    @pytest.mark.parametrize(
        "date_input, expected",
        [
            # 2026-08-17 (Poniedziałek) -> True
            ("2026-08-17", True),
            (date(2026, 8, 17), True),
            (datetime(2026, 8, 17, 15, 0, 0), True),
            # 2026-08-18 (Wtorek) -> True
            ("2026-08-18", True),
            # 2026-08-19 (Środa) -> True
            ("2026-08-19", True),
            # 2026-08-20 (Czwartek) -> True
            ("2026-08-20", True),
            # 2026-08-21 (Piątek) -> True
            ("2026-08-21", True),
            (date(2026, 8, 21), True),
            (datetime(2026, 8, 21, 23, 59, 59), True),
            # 2026-08-22 (Sobota) -> False (w domyślnej konfiguracji pon-pt)
            ("2026-08-22", False),
            (date(2026, 8, 22), False),
            (datetime(2026, 8, 22, 15, 0, 0), False),
            # 2026-08-23 (Niedziela) -> False
            ("2026-08-23", False),
            (date(2026, 8, 23), False),
            (datetime(2026, 8, 23, 0, 0, 0), False),
            # Nieprawidłowe wejścia
            ("niepoprawna-data", False),
        ],
    )
    def test_is_weekday_default_config(self, date_input, expected):
        with patch.object(AutoReportService, "get_global_config", return_value={
            'active_days': [0, 1, 2, 3, 4],
            'enabled_lines': ['AGRO', 'PSD'],
            'agro_enabled': True,
            'psd_enabled': True
        }):
            assert AutoReportService.is_weekday(date_input) == expected
            assert AutoReportService.is_report_day(date_input) == expected

    def test_custom_active_days_configuration(self):
        # Konfiguracja: wysyłka tylko w poniedziałki (0) i soboty (5)
        custom_config = {
            'active_days': [0, 5],
            'enabled_lines': ['AGRO'],
            'agro_enabled': True,
            'psd_enabled': False
        }
        with patch.object(AutoReportService, "get_global_config", return_value=custom_config):
            # Poniedziałek 2026-08-17 -> True
            assert AutoReportService.is_report_day("2026-08-17") is True
            # Wtorek 2026-08-18 -> False
            assert AutoReportService.is_report_day("2026-08-18") is False
            # Sobota 2026-08-22 -> True
            assert AutoReportService.is_report_day("2026-08-22") is True
            # Niedziela 2026-08-23 -> False
            assert AutoReportService.is_report_day("2026-08-23") is False

    def test_is_line_enabled(self):
        # Tylko linia AGRO włączona
        with patch.object(AutoReportService, "get_global_config", return_value={
            'active_days': [0, 1, 2, 3, 4],
            'enabled_lines': ['AGRO'],
            'agro_enabled': True,
            'psd_enabled': False
        }):
            assert AutoReportService.is_line_enabled('AGRO') is True
            assert AutoReportService.is_line_enabled('PSD') is False
            assert AutoReportService.is_line_enabled('agro') is True

    def test_send_shift1_report_skips_when_line_disabled(self):
        with patch.object(AutoReportService, "is_line_enabled", return_value=False):
            success, msg = AutoReportService.send_shift1_report_at_1500(linia="PSD", date_str="2026-08-17", force=False)
            assert success is True
            assert "wyłączony w konfiguracji" in msg

    def test_send_shift1_report_skips_on_inactive_day_unless_forced(self):
        saturday_str = "2026-08-22"

        with patch.object(AutoReportService, "is_line_enabled", return_value=True), \
             patch.object(AutoReportService, "is_report_day", return_value=False), \
             patch.object(AutoReportService, "is_1500_report_sent", return_value=False), \
             patch.object(AutoReportService, "get_default_recipients", return_value=["test@example.com"]):
            
            success, msg = AutoReportService.send_shift1_report_at_1500(linia="AGRO", date_str=saturday_str, force=False)
            assert success is True
            assert "pominięty" in msg
            assert "harmonogramie wysyłek" in msg

    def test_send_shift1_report_allowed_on_weekend_if_forced(self):
        saturday_str = "2026-08-22"

        with patch.object(AutoReportService, "is_line_enabled", return_value=True), \
             patch.object(AutoReportService, "is_report_day", return_value=False), \
             patch.object(AutoReportService, "is_1500_report_sent", return_value=False), \
             patch.object(AutoReportService, "get_default_recipients", return_value=[]):
            
            # Bez odbiorców zwróci błąd walidacji, ale nie zostanie pominięty
            success, msg = AutoReportService.send_shift1_report_at_1500(linia="AGRO", date_str=saturday_str, force=True)
            assert success is False
            assert "Brak skonfigurowanych odbiorcow" in msg


class TestAutoReportServiceLockingAndHistory:
    """Testy weryfikujące mechanizm atomowej rezerwacji i zabezpieczenia historii wysyłek."""

    def test_send_shift1_report_skips_when_claim_fails(self):
        with patch.object(AutoReportService, "is_line_enabled", return_value=True), \
             patch.object(AutoReportService, "is_report_day", return_value=True), \
             patch.object(AutoReportService, "is_1500_report_sent", return_value=False), \
             patch.object(AutoReportService, "get_default_recipients", return_value=["test@example.com"]), \
             patch.object(AutoReportService, "claim_report_execution", return_value=False):
            
            success, msg = AutoReportService.send_shift1_report_at_1500(linia="AGRO", date_str="2026-08-25", force=False)
            assert success is True
            assert "w trakcie wysyłki lub w okresie cooldownu" in msg

    def test_is_1500_report_sent_only_for_sent_status(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Przypadek 1: znaleziono wiersz o statusie SENT -> True
        mock_cursor.fetchone.return_value = {'id': 1}
        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn):
            assert AutoReportService.is_1500_report_sent("AGRO", "2026-08-25") is True

        # Przypadek 2: brak wiersza o statusie SENT -> False
        mock_cursor.fetchone.return_value = None
        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn):
            assert AutoReportService.is_1500_report_sent("AGRO", "2026-08-25") is False

    def test_claim_report_execution_returns_false_if_already_sent(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {'id': 1, 'status': 'SENT', 'age_min': 50}
        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn):
            assert AutoReportService.claim_report_execution("AGRO", "2026-08-25", "15:00") is False

    def test_claim_report_execution_returns_false_if_in_progress_recently(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {'id': 1, 'status': 'IN_PROGRESS', 'age_min': 3}
        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn):
            assert AutoReportService.claim_report_execution("AGRO", "2026-08-25", "15:00") is False

    def test_claim_report_execution_returns_true_if_no_record(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_cursor.fetchone.return_value = None
        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn):
            assert AutoReportService.claim_report_execution("AGRO", "2026-08-25", "15:00") is True

    def test_set_schedule_does_not_delete_history(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("app.services.auto_report_service.get_db_connection", return_value=mock_conn), \
             patch("app.services.auto_report_service.audit_log"):
            
            ok, msg = AutoReportService.set_schedule(linia="AGRO", date_str="2026-08-25", scheduled_time="15:30", is_paused=False)
            assert ok is True

            # Sprawdź wykonane zapytania SQL - nie powinno być DELETE FROM auto_report_history
            executed_queries = [call[0][0] for call in mock_cursor.execute.call_args_list]
            assert not any("DELETE FROM auto_report_history" in q for q in executed_queries)

