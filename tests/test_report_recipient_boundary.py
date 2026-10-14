"""Disabled recipients and failed lookups cannot activate an unrelated fallback."""
from unittest.mock import patch
from app.services.auto_report.auto_report_recipients_service import AutoReportRecipientsService


def test_all_disabled_blocks_system_fallback(monkeypatch):
    monkeypatch.setenv('DEFAULT_REPORT_RECIPIENTS', 'fallback@example.com')
    with patch('app.repositories.user_email_settings_repository.UserEmailSettingsRepository.get_all_recipients',
               return_value=[{'email': 'disabled@example.com', 'aktywny': 0}]):
        assert AutoReportRecipientsService.get_default_recipients() == []


def test_failed_dictionary_lookup_blocks_fallback(monkeypatch):
    monkeypatch.setenv('DEFAULT_REPORT_RECIPIENTS', 'fallback@example.com')
    with patch('app.repositories.user_email_settings_repository.UserEmailSettingsRepository.get_all_recipients',
               side_effect=OSError('unavailable')):
        assert AutoReportRecipientsService.get_default_recipients() == []


def test_active_dictionary_is_deduplicated():
    with patch('app.repositories.user_email_settings_repository.UserEmailSettingsRepository.get_all_recipients',
               return_value=[{'email': 'A@example.com', 'aktywny': 1},
                             {'email': 'a@example.com', 'aktywny': 1},
                             {'email': 'b@example.com', 'aktywny': 0}]):
        assert AutoReportRecipientsService.get_default_recipients() == ['A@example.com']
