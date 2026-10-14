"""Forced reports still need ownership, complete files and escaped user text."""
from unittest.mock import patch
import pytest
from app.services.auto_report.auto_report_dispatcher_service import AutoReportDispatcherService
from app.services.email_report_builder import EmailReportBuilder


def test_force_does_not_bypass_execution_claim():
    with patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.is_report_sent', return_value=False), patch(
            'app.services.auto_report.auto_report_recipients_service.AutoReportRecipientsService.get_default_recipients', return_value=['a@example.com']), patch(
            'app.services.auto_report.auto_report_history_service.AutoReportHistoryService.claim_report_execution', return_value=False) as claim, patch(
            'app.services.email_service.EmailService.send_report_email') as send:
        AutoReportDispatcherService.send_shift1_report_at_1500('AGRO', '2026-10-03', force=True)
        claim.assert_called_once_with('AGRO', '2026-10-03', '15:00')
        send.assert_not_called()


def test_incomplete_generated_report_is_not_sent():
    with patch('app.services.auto_report.auto_report_history_service.AutoReportHistoryService.is_report_sent', return_value=False), patch(
            'app.services.auto_report.auto_report_recipients_service.AutoReportRecipientsService.get_default_recipients', return_value=['a@example.com']), patch(
            'app.services.auto_report.auto_report_history_service.AutoReportHistoryService.claim_report_execution', return_value=True), patch(
            'app.services.auto_report.auto_report_history_service.AutoReportHistoryService.mark_report_failed') as failed, patch(
            'app.services.shift_close_service._load_shift_notes', return_value=''), patch(
            'app.services.shift_close_service._generate_report_files', return_value=(None, None, None)), patch(
            'app.services.email_service.EmailService.send_report_email') as send:
        assert not AutoReportDispatcherService.send_shift1_report_at_1500('AGRO', '2026-10-03', force=True)[0]
        failed.assert_called_once()
        send.assert_not_called()


def test_report_text_cannot_inject_html():
    body = EmailReportBuilder.build_shift_report_html(
        'AGRO', '2026-10-03', '<b>leader</b>', 1, 2, [], 0,
        '<img src="https://example.com/tracker">\nNext line', ['<a>file</a>'])
    assert '<b>leader</b>' not in body
    assert '<img src="https://example.com/tracker">' not in body
    assert '&lt;img' in body
    assert '<a>file</a>' not in body


def test_report_close_does_not_hide_database_failure():
    from app.services.shift_close_service import _suspend_previous_day_plans
    with patch('app.services.shift_close_service.get_db_connection', side_effect=OSError('unavailable')):
        with pytest.raises(OSError):
            _suspend_previous_day_plans('2026-10-03', linia='AGRO', strict=True)
        assert _suspend_previous_day_plans('2026-10-03', linia='AGRO') is None
