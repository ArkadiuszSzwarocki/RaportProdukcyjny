from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

from app.services.daily_report_scheduler import run_daily_reports
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService as History
from app.services.auto_report_service import AutoReportService as Production
from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository as Settings
from app.services.osip_report_email_service import OsipReportEmailService as Warehouse
from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService as Schedule


@pytest.mark.parametrize('hour,minute', [(1, 50), (14, 59), (15, 1), (18, 25), (23, 59)])
def test_no_automatic_dispatch_outside_1500(hour, minute):
    cfg = SimpleNamespace(is_active=True, daily_report_enabled=True, daily_report_time='15:00', last_daily_report_date=None)
    with patch.object(Production, 'get_global_config', return_value={'enabled_lines': ['AGRO']}), patch.object(Production, 'get_schedule', return_value={'scheduled_time': '15:00'}), patch.object(Production, 'is_report_day', return_value=True), patch.object(Settings, 'get_settings', return_value=cfg), patch.object(Production, 'send_shift1_report_at_1500') as production, patch.object(Warehouse, 'send_daily_warehouse_summary_report') as warehouse:
        run_daily_reports(datetime(2026, 10, 12, hour, minute, tzinfo=ZoneInfo('Europe/Warsaw')))
    production.assert_not_called()
    warehouse.assert_not_called()


@pytest.mark.parametrize('status', ['FAILED', 'IN_PROGRESS', 'SENT', 'SKIPPED_EMPTY'])
def test_old_attempt_cannot_be_reclaimed(status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {'id': 10, 'status': status, 'age_min': 10000}
    with patch('app.services.auto_report.auto_report_history_service.get_db_connection', return_value=conn), patch.object(History, 'ensure_history_tables'):
        assert not History.claim_report_execution('AGRO', '2026-10-12')
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list)


@pytest.mark.parametrize('raises', [False, True])
def test_warehouse_failure_is_reserved_and_not_retried(raises):
    cfg = SimpleNamespace(is_active=True, daily_report_enabled=True, daily_report_time='15:00', last_daily_report_date=None)
    with patch.object(Production, 'get_global_config', return_value={'enabled_lines': []}), patch.object(Production, 'get_schedule', return_value={}), patch.object(Settings, 'get_settings', return_value=cfg), patch.object(History, 'claim_report_execution', side_effect=[True, False]) as claim, patch.object(History, 'mark_report_failed') as failed, patch.object(Warehouse, 'send_daily_warehouse_summary_report', return_value=(False, 'SMTP error'), side_effect=RuntimeError('SMTP error') if raises else None) as send:
        # Two different scheduler invocations, including another worker/restart.
        run_daily_reports(datetime(2026, 10, 12, 15, 0, 2, tzinfo=ZoneInfo('Europe/Warsaw')))
        run_daily_reports(datetime(2026, 10, 12, 15, 0, 12, tzinfo=ZoneInfo('Europe/Warsaw')))
    send.assert_called_once()
    failed.assert_called_once()
    assert claim.call_args.args == ('MAGAZYN', '2026-10-12', '15:00')


def test_postponed_production_runs_only_at_selected_minute():
    with patch.object(Production, 'get_global_config', return_value={'enabled_lines': ['AGRO']}), patch.object(Production, 'get_schedule', return_value={'is_paused': False, 'scheduled_time': '18:00'}), patch.object(Production, 'is_report_day', return_value=True), patch.object(Production, 'is_1500_report_sent', return_value=False), patch.object(Production, 'send_shift1_report_at_1500') as send, patch.object(Settings, 'get_settings', return_value=SimpleNamespace(is_active=False)):
        for hour, minute in [(15, 0), (17, 59), (18, 1), (23, 59)]:
            run_daily_reports(datetime(2026, 10, 12, hour, minute, tzinfo=ZoneInfo('Europe/Warsaw')))
        send.assert_not_called()
        run_daily_reports(datetime(2026, 10, 12, 16, 0, tzinfo=ZoneInfo('UTC')))
    send.assert_called_once_with(linia='AGRO', date_str='2026-10-12')


def test_invalid_time_is_rejected_without_database_writes():
    with patch('app.services.auto_report.auto_report_schedule_service.get_db_connection') as connect:
        ok, _ = Schedule.set_schedule('AGRO', '2026-10-12', '25:00')
    assert not ok
    connect.assert_not_called()


def test_postponement_cannot_wrap_into_next_day():
    cfg = {'scheduled_time': '23:45'}
    with patch.object(Schedule, 'get_schedule', return_value=cfg), patch.object(Schedule, 'set_schedule') as save:
        ok, _, _ = Schedule.postpone_report('AGRO', '2099-10-12', add_minutes=30)
    assert not ok
    save.assert_not_called()


def test_warehouse_uses_its_selected_hour():
    cfg = SimpleNamespace(is_active=True, daily_report_enabled=True, daily_report_time='17:30', last_daily_report_date=None)
    with patch.object(Production, 'get_global_config', return_value={'enabled_lines': []}), patch.object(Production, 'get_schedule', return_value={}), patch.object(Settings, 'get_settings', return_value=cfg), patch.object(History, 'claim_report_execution', return_value=True), patch.object(History, 'mark_report_sent'), patch.object(Warehouse, 'send_daily_warehouse_summary_report', return_value=(True, 'ok')) as send:
        run_daily_reports(datetime(2026, 10, 12, 15, 0, tzinfo=ZoneInfo('Europe/Warsaw')))
        send.assert_not_called()
        run_daily_reports(datetime(2026, 10, 12, 17, 30, tzinfo=ZoneInfo('Europe/Warsaw')))
        run_daily_reports(datetime(2026, 10, 12, 17, 31, tzinfo=ZoneInfo('Europe/Warsaw')))
    send.assert_called_once()


@pytest.mark.require_db
def test_daily_reservation_survives_failure_and_a_second_connection():
    # Dedicated local test DB supplied by the launcher, never production.
    from app.core.database import get_db_connection
    import uuid
    report_type = 'test-' + uuid.uuid4().hex[:20]
    try:
        assert History.claim_report_execution('MAGAZYN', '2026-10-12', report_type)
        History.mark_report_failed('MAGAZYN', '2026-10-12', report_type, 'simulated SMTP failure')
        assert not History.claim_report_execution('MAGAZYN', '2026-10-12', report_type)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE auto_report_history SET created_at = %s WHERE typ_raportu = %s', ('2020-01-01', report_type))
            conn.commit()
        finally:
            conn.close()
        assert not History.claim_report_execution('MAGAZYN', '2026-10-12', report_type)
    finally:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM auto_report_history WHERE typ_raportu = %s', (report_type,))
            conn.commit()
        finally:
            conn.close()
