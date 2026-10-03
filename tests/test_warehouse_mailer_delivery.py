"""SMTP acceptance, attachment integrity and transport cleanup regressions."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from app.services.warehouse_reports.warehouse_report_mailer import WarehouseReportMailer


@pytest.fixture
def transport():
    config = SimpleNamespace(smtp_server='smtp.example.com', smtp_username='sender@example.com',
                             smtp_password='test', smtp_port=465, smtp_security='SSL', sender_name='Test')
    server = MagicMock()
    server.sendmail.return_value = {}
    with patch('app.services.warehouse_reports.warehouse_report_mailer.smtp_target_allowed', return_value=(True, '')), patch(
            'app.services.warehouse_reports.warehouse_report_mailer.smtplib.SMTP_SSL', return_value=server) as connect:
        yield config, server, connect


def send(config, attachments=None):
    return WarehouseReportMailer.send_raw_email(config, ['receiver@example.com'], 'Test', 'Test', attachments)


def test_acceptance_survives_quit_failure(transport):
    config, server, connect = transport
    server.quit.side_effect = OSError('closed')
    assert send(config)[0] is True
    server.sendmail.assert_called_once()
    server.close.assert_called_once()
    assert connect.call_args.kwargs['context'].check_hostname is True


def test_partial_refusal_is_not_success(transport):
    config, server, _ = transport
    server.sendmail.return_value = {'receiver@example.com': (550, b'rejected')}
    assert send(config)[0] is False
    server.quit.assert_called_once()


def test_missing_attachment_prevents_connection(transport, tmp_path):
    config, server, connect = transport
    assert send(config, [(str(tmp_path / 'missing.pdf'), 'report.pdf')])[0] is False
    connect.assert_not_called()
    server.sendmail.assert_not_called()


def test_login_failure_closes_transport(transport):
    config, server, _ = transport
    server.login.side_effect = OSError('failed')
    assert send(config)[0] is False
    server.sendmail.assert_not_called()
    server.quit.assert_called_once()


def test_lowercase_tls_configuration_still_encrypts_transport(transport):
    config, server, ssl_connect = transport
    config.smtp_security = 'tls'
    config.smtp_port = 587
    with patch('app.services.warehouse_reports.warehouse_report_mailer.smtplib.SMTP', return_value=server):
        assert send(config)[0] is True
    ssl_connect.assert_not_called()
    server.starttls.assert_called_once()
    assert server.starttls.call_args.kwargs['context'].check_hostname is True


def test_blocked_destination_does_not_connect(transport):
    config, _, connect = transport
    with patch('app.services.warehouse_reports.warehouse_report_mailer.smtp_target_allowed', return_value=(False, 'Blocked')):
        assert send(config) == (False, 'Blocked')
    connect.assert_not_called()


def test_daily_report_generation_failure_does_not_send_or_mark_sent():
    from app.services.osip_report_email_service import OsipReportEmailService
    settings = MagicMock()
    settings.get_settings.return_value = SimpleNamespace(is_active=True, is_configured=True, recipients_list=['receiver@example.com'])
    activity = {'has_activity': True, 'all_documents': [{'raw_dostawa': {'id': 1}}]}
    with patch('app.services.osip_report_email_service.WarehouseActivityQueryService.get_daily_warehouse_activity', return_value=activity), patch(
            'app.services.osip_report_email_service.WarehouseEmailTemplateBuilder.build_daily_summary_report_html', return_value='Test'), patch(
            'app.services.osip_report_email_service.WarehousePdfReportBuilder.generate_delivery_pdf', return_value=None), patch(
            'app.services.osip_report_email_service.WarehouseReportMailer.send_raw_email') as send_email:
        assert OsipReportEmailService(settings_repo=settings).send_daily_warehouse_summary_report('2000-01-02', force=True)[0] is False
    send_email.assert_not_called()
    settings.update_last_daily_report_date.assert_not_called()
    assert 'daily_report_2000-01-02' not in OsipReportEmailService._active_dispatches
