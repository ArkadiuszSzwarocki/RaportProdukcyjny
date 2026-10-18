"""Regression coverage for duplicate submissions and missing report absences."""
from datetime import date, timedelta
from flask import Flask
from unittest.mock import MagicMock, patch
import pytest
from scripts.reports.attendance_data import merge_absences, load_daily_absences
from app.services.leave_request_service import LeaveRequestService
from app.services.attendance_write_service import insert_attendance_once


def test_report_lease_never_disconnects_other_instances():
    from app.core.report_daemon import _acquire_report_lease
    conn = MagicMock(); conn.database = 'isolated_test'
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (0,)
    with patch('app.db.get_db_connection', return_value=conn):
        assert _acquire_report_lease() is None
    assert not any('KILL' in call.args[0].upper() for call in cursor.execute.call_args_list)
    conn.close.assert_called_once()


def test_report_lease_requires_both_legacy_and_database_lock():
    from app.core.report_daemon import _acquire_report_lease
    conn = MagicMock(); conn.database = 'isolated_test'
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,), (1,)]
    with patch('app.db.get_db_connection', return_value=conn):
        assert _acquire_report_lease() is conn
    assert [call.args[1][0] for call in cursor.execute.call_args_list] == [
        'auto_report_daemon_leader', 'auto_report_daemon_leader_isolated_test']


@pytest.fixture
def app_context():
    app = Flask(__name__)
    with app.app_context():
        yield app


def row(**values):
    return dict(pracownik_id=1, pracownik='Test', typ='L4', komentarz='',
                assigned='AGRO', widoczny_agro=1, **values)


def test_repeated_l4_and_materialized_request_appear_once():
    attendance = [row(), row(), row()]
    assert len(merge_absences(attendance, [], 'AGRO')) == 1
    materialized = row(); materialized.update(typ='Urlop', komentarz='Auto z wniosku #7')
    request = row(); request.update(request_id=7, typ='Urlop zaległy', komentarz='Wypoczynek')
    assert merge_absences([materialized], [request], 'AGRO') == [
        {'pracownik': 'Test', 'typ': 'Urlop zaległy', 'komentarz': 'Wypoczynek'}]


def test_psd_assignment_overrides_default_agro_visibility():
    entry = row(); entry['assigned'] = 'PSD'
    assert merge_absences([entry], [], 'PSD')[0]['typ'] == 'L4'
    assert merge_absences([entry], [], 'AGRO') == []


def test_unscheduled_l4_uses_employee_visibility_and_overtime_is_not_absence():
    entry = row(); entry['assigned'] = None
    overtime = row(); overtime['typ'] = 'Nadgodziny'
    assert len(merge_absences([entry, overtime], [], 'AGRO')) == 1


def test_distinct_private_exits_remain_visible():
    first = row(); first.update(typ='Wyjscie prywatne',time_from='10:00:00',time_to='11:00:00')
    second = dict(first, time_from='13:00:00',time_to='14:00:00')
    assert len(merge_absences([first, first, second], [], 'AGRO')) == 2


def test_report_query_failure_is_not_silently_empty():
    conn = MagicMock(); conn.cursor.return_value.execute.side_effect = RuntimeError('read failed')
    with pytest.raises(RuntimeError):
        load_daily_absences(conn, '2040-01-02', 'AGRO')
    conn.cursor.return_value.close.assert_called_once()


def test_duplicate_insert_is_noop_and_private_exit_intervals_are_compared():
    cursor = MagicMock(); cursor.fetchone.return_value = (9,)
    assert not insert_attendance_once(cursor, date(2040,1,2), 1, 'L4', 8, '')
    assert not any('INSERT' in str(call) for call in cursor.execute.call_args_list)
    cursor.reset_mock(); cursor.fetchone.return_value = None
    assert insert_attendance_once(cursor, date(2040,1,2), 1, 'Wyjscie prywatne', 1, '', '10:00', '11:00')
    assert cursor.execute.call_args_list[0].args[1][-2:] == ('10:00', '11:00')


@pytest.mark.parametrize('status', ['approved', 'rejected', 'revoked'])
def test_repeated_approval_does_not_change_counters_or_history(app_context, status):
    conn = MagicMock(); cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (1,date(2040,1,2),date(2040,1,2),'Urlop',status)
    with patch('app.services.leave_request_service.get_db_connection', return_value=conn):
        success, _ = LeaveRequestService.approve_leave_request(5, 1)
    assert success == (status == 'approved')
    assert all(not call.args[0].lstrip().startswith(('UPDATE','INSERT','ALTER')) for call in cursor.execute.call_args_list)
    conn.commit.assert_not_called()


def test_approval_failure_rolls_back_all_changes(app_context):
    conn = MagicMock(); cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [(1,date(2040,1,2),date(2040,1,2),'Urlop','pending'), (1,)]
    with patch('app.services.leave_request_service.get_db_connection', return_value=conn), patch.object(
            LeaveRequestService, '_create_absence_records', side_effect=RuntimeError('insert failed')):
        assert not LeaveRequestService.approve_leave_request(5, 1)[0]
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once()
    assert not any('ALTER TABLE' in call.args[0] for call in cursor.execute.call_args_list)


def test_manual_email_adds_generated_pdf_even_if_only_excel_was_selected(tmp_path):
    from app.services.report_attachment_service import ensure_manual_pdf
    pdf = tmp_path / 'Raport_AGRO_2040-01-02.pdf'; pdf.write_bytes(b'%PDF-1.4\n%%EOF')
    with patch('app.services.shift_close_service._generate_report_files', return_value=(None,None,pdf)):
        assert ensure_manual_pdf(['report.xlsx'], '2040-01-02', 'AGRO', '', 'Test') == ['report.xlsx',str(pdf)]


def test_manual_email_fails_when_pdf_is_missing_or_invalid(tmp_path):
    from app.services.report_attachment_service import ensure_manual_pdf
    with patch('app.services.shift_close_service._generate_report_files', return_value=(None,None,None)):
        with pytest.raises(ValueError, match='nie został wysłany'):
            ensure_manual_pdf([], '2040-01-02', 'AGRO', '', 'Test')
    pdf = tmp_path / 'Raport_AGRO_2040-01-02.pdf'; pdf.write_bytes(b'broken')
    with pytest.raises(ValueError, match='Nieprawidłowy PDF'):
        ensure_manual_pdf([str(pdf)], '2040-01-02', 'AGRO', '', 'Test')


def test_last_agro_assignment_takes_priority_over_hidden_employee_flag():
    entry = row(); entry['widoczny_agro'] = 0
    assert merge_absences([entry], [], 'AGRO')[0]['typ'] == 'L4'
    entry['assigned'] = 'PSD'
    assert merge_absences([entry], [], 'AGRO') == []


def test_mysql_time_interval_is_formatted_as_clock_time():
    entry = row(); entry.update(typ='Wyjście prywatne',time_from=timedelta(hours=8),time_to=timedelta(hours=9))
    assert merge_absences([entry], [], 'AGRO')[0]['komentarz'] == '(08:00 - 09:00)'


def test_local_copy_does_not_start_report_scheduler(monkeypatch):
    from app.core.report_daemon import start_report_scheduler
    monkeypatch.delenv('ENABLE_AUTO_REPORT_SCHEDULER', raising=False)
    with patch('app.core.report_daemon.threading.Thread') as thread:
        assert start_report_scheduler(Flask(__name__)) is False
    thread.assert_not_called()


def test_bad_encryption_key_cannot_start_scheduler_or_claim_report(monkeypatch):
    from app.core.report_daemon import start_report_scheduler
    monkeypatch.setenv('ENABLE_AUTO_REPORT_SCHEDULER', 'true')
    monkeypatch.delenv('ENCRYPTION_KEY', raising=False)
    with patch('app.core.report_daemon.threading.Thread') as thread:
        assert start_report_scheduler(Flask(__name__)) is False
    thread.assert_not_called()


def test_designated_scheduler_starts_once_with_valid_key(monkeypatch):
    from app.core.report_daemon import start_report_scheduler
    from cryptography.fernet import Fernet
    monkeypatch.setenv('ENABLE_AUTO_REPORT_SCHEDULER', 'true')
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    app = Flask(__name__)
    with patch('app.core.report_daemon.threading.Thread') as thread:
        assert start_report_scheduler(app)
        assert start_report_scheduler(app)
    thread.return_value.start.assert_called_once()


def test_email_mime_contains_pdf_attachment(tmp_path):
    from email import message_from_string
    from app.services.email_service import EmailService
    pdf = tmp_path / 'Raport_AGRO_2040-01-02.pdf'; pdf.write_bytes(b'%PDF-1.4\n%%EOF')
    config = dict(configured=True,server='smtp.example.com',port=465,security='SSL',
                  username='sender@example.com',password='test-only',sender_name='Test')
    service = EmailService()
    with patch.object(service, 'get_smtp_config_for_user', return_value=config), patch(
            'app.services.email_service.smtp_target_allowed', return_value=(True,'')), patch(
            'app.services.email_service.secure_smtp_connection') as smtp, patch(
            'app.services.email_log_service.EmailLogService.log_email_attempt'):
        smtp.return_value.sendmail.return_value = {}
        ok, _ = service.send_report_email(['recipient@example.com'], 'Raport AGRO', 'Test', [str(pdf)])
        assert ok
        mail = message_from_string(smtp.return_value.sendmail.call_args.args[2])
    attachments = [part for part in mail.walk() if part.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == 'application/pdf'
    assert attachments[0].get_payload(decode=True).startswith(b'%PDF-')


@pytest.mark.parametrize('pdf_available', [True, False])
def test_manual_report_route_never_sends_without_pdf(tmp_path, monkeypatch, pdf_available):
    from flask import Blueprint
    from app.blueprints.main.reporting import register_main_reporting_routes
    from app.services import shift_close_service
    from app.services.auto_report_service import AutoReportService
    from app.services.email_service import EmailService
    from app.repositories.downtime_repository import DowntimeRepository
    from app.services.email_report_builder import EmailReportBuilder
    app = Flask(__name__); app.secret_key = 'test-only'
    bp = Blueprint('main',__name__)
    bp.add_url_rule('/', endpoint='index', view_func=lambda:'Home')
    register_main_reporting_routes(bp); app.register_blueprint(bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True,login='Test',rola='lider',user_id=1)
    pdf = tmp_path / 'Raport_AGRO_2040-01-02.pdf'; pdf.write_bytes(b'%PDF-1.4\n%%EOF')
    monkeypatch.setattr(AutoReportService,'has_report_data',lambda *a:True)
    monkeypatch.setattr(shift_close_service,'get_shift_actual_production',lambda *a,**k:dict(suma_zasyp=1,suma_workowanie=1,palety_count=1))
    monkeypatch.setattr(shift_close_service,'_get_leader_name',lambda *a,**k:('Test',''))
    monkeypatch.setattr(shift_close_service,'_generate_report_files',lambda *a,**k:(None,None,pdf if pdf_available else None))
    monkeypatch.setattr(DowntimeRepository,'get_downtimes',lambda *a:[])
    monkeypatch.setattr(EmailReportBuilder,'build_shift_report_html',lambda **k:'Test')
    with patch.object(EmailService,'send_report_email',return_value=(True,'OK')) as send:
        response = client.post('/raport/zakoncz_zmiane/wyslij',data=dict(linia='AGRO',date_str='2040-01-02',to_emails='test@example.com'))
    assert response.status_code == 302
    if pdf_available:
        assert send.call_args.kwargs['attachments'] == [str(pdf)]
    else:
        send.assert_not_called()
