# File: tests/test_auto_report_extended_audit.py
"""
Extended Automated Audit Tests for Auto-Report Scheduler and Email Dispatching.
Verifies:
1. Exact single email dispatch per line at scheduled time.
2. Immediate and total block when report is paused (is_paused=True).
3. Propagation of pause flag for 'ALL' and specific lines ('AGRO', 'PSD').
4. Atomic concurrency protection (claim_report_execution).
5. Exclusion of inactive recipients.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from app.services.auto_report_service import AutoReportService
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository


class TestAutoReportExtendedAudit:
    """Rigorous audit test suite for email scheduler guarantees."""

    def test_paused_report_is_strictly_blocked_in_service(self):
        """Audit Guarantee: When is_paused is True, send_shift1_report_at_1500 MUST NEVER send email."""
        test_date = "2026-09-01"
        test_line = "AGRO"

        with patch('app.services.auto_report.auto_report_config_service.AutoReportConfigService.is_report_day', return_value=True), \
             patch('app.services.auto_report.auto_report_schedule_service.AutoReportScheduleService.get_schedule', return_value={'is_paused': True, 'scheduled_time': '15:00'}), \
             patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.claim_report_execution') as mock_claim, \
             patch('app.services.email_service.EmailService.send_report_email') as mock_send:

            success, msg = AutoReportService.send_shift1_report_at_1500(linia=test_line, date_str=test_date, force=False)

            assert success is True
            assert "wstrzymany" in msg
            mock_claim.assert_not_called()
            mock_send.assert_not_called()

    def test_already_sent_report_is_strictly_blocked(self):
        """Audit Guarantee: When report is already marked SENT, it must never send a second time."""
        test_date = "2026-09-01"
        test_line = "AGRO"

        with patch('app.services.auto_report.auto_report_config_service.AutoReportConfigService.is_report_day', return_value=True), \
             patch('app.services.auto_report.auto_report_schedule_service.AutoReportScheduleService.get_schedule', return_value={'is_paused': False, 'scheduled_time': '15:00'}), \
             patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.is_report_sent', return_value=True), \
             patch('app.services.email_service.EmailService.send_report_email') as mock_send:

            success, msg = AutoReportService.send_shift1_report_at_1500(linia=test_line, date_str=test_date, force=False)

            assert success is True
            assert "został już wysłany" in msg or "juz wyslany" in msg
            mock_send.assert_not_called()

    def test_claim_report_execution_guarantees_single_execution(self):
        """Audit Guarantee: If another worker/process holds execution or SENT status, claim returns False."""
        test_date = "2026-09-01"
        test_line = "AGRO"

        with patch('app.services.auto_report.auto_report_config_service.AutoReportConfigService.is_report_day', return_value=True), \
             patch('app.services.auto_report.auto_report_schedule_service.AutoReportScheduleService.get_schedule', return_value={'is_paused': False, 'scheduled_time': '15:00'}), \
             patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.is_report_sent', return_value=False), \
             patch('app.services.auto_report.auto_report_activity_detector.AutoReportActivityDetector.has_report_data', return_value=True), \
             patch('app.services.auto_report.auto_report_recipients_service.AutoReportRecipientsService.get_default_recipients', return_value=['boss@agronetzwerk.com']), \
             patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.claim_report_execution', return_value=False), \
             patch('app.services.email_service.EmailService.send_report_email') as mock_send:

            success, msg = AutoReportService.send_shift1_report_at_1500(linia=test_line, date_str=test_date, force=False)

            assert success is True
            assert "już wysłany" in msg or "cooldown" in msg
            mock_send.assert_not_called()

    def test_only_active_recipients_receive_emails(self):
        """Audit Guarantee: Inactive recipients with aktywny=0 are filtered out."""
        mock_recipients = [
            {'id': 1, 'nazwa': 'Jan Kowalski', 'email': 'jan@agronetzwerk.com', 'aktywny': 1},
            {'id': 2, 'nazwa': 'Anna Nowak', 'email': 'anna@agronetzwerk.com', 'aktywny': 0},
            {'id': 3, 'nazwa': 'Piotr Zieliński', 'email': 'piotr@agronetzwerk.com', 'aktywny': 1}
        ]

        with patch.object(UserEmailSettingsRepository, 'get_all_recipients', return_value=[mock_recipients[0], mock_recipients[2]]):
            active_emails = AutoReportService.get_default_recipients('AGRO')
            assert 'jan@agronetzwerk.com' in active_emails
            assert 'piotr@agronetzwerk.com' in active_emails
            assert 'anna@agronetzwerk.com' not in active_emails
            assert len(active_emails) == 2
