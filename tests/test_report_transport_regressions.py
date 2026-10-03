"""SMTP acceptance, partial refusal and selected attachments have distinct outcomes."""
from unittest.mock import MagicMock, patch
import pytest
from app.services.email_service import EmailService


@pytest.fixture
def transport():
    service = EmailService()
    config = {'configured': True, 'server': 'smtp.example.com', 'port': 465,
              'security': 'SSL', 'username': 'sender@example.com', 'password': 'test-only'}
    server = MagicMock()
    server.sendmail.return_value = {}
    with patch.object(service, 'get_smtp_config_for_user', return_value=config), patch(
            'app.services.email_service.smtp_target_allowed', return_value=(True, '')), patch(
            'app.services.email_service.smtplib.SMTP_SSL', return_value=server), patch(
            'app.services.email_log_service.EmailLogService.log_email_attempt'):
        yield service, server


def test_missing_attachment_does_not_send(transport, tmp_path):
    service, server = transport
    assert not service.send_report_email(['a@example.com'], 'Raport', '<p>test</p>',
                                         [str(tmp_path / 'missing.pdf')])[0]
    server.sendmail.assert_not_called()


def test_partial_refusal_is_not_complete_success(transport):
    service, server = transport
    server.sendmail.return_value = {'b@example.com': (550, b'Rejected')}
    assert not service.send_report_email(['a@example.com', 'b@example.com'], 'Raport', 'test')[0]


def test_quit_failure_after_acceptance_still_reports_success(transport):
    service, server = transport
    server.quit.side_effect = OSError('connection closed after acceptance')
    assert service.send_report_email(['a@example.com'], 'Raport', 'test')[0]
    server.sendmail.assert_called_once()
