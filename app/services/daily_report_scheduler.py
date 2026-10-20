"""One automatic attempt per report/day, only during its scheduled minute."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _is_due(now, scheduled_time):
    try:
        target = datetime.strptime(str(scheduled_time)[:5], '%H:%M')
    except (ValueError, TypeError):
        return False
    return (now.hour, now.minute) == (target.hour, target.minute)


def run_daily_reports(now):
    # Daemon supplies an aware clock. Explicit zone avoids host-dependent schedules.
    now = now.astimezone(ZoneInfo('Europe/Warsaw'))
    date_str = now.strftime('%Y-%m-%d')
    # The standalone QNAP report owner also calls this entry point directly.
    from flask import current_app, has_app_context
    if has_app_context():
        from app.services.warehouse_reports.completed_movement_mailer import CompletedMovementMailer
        CompletedMovementMailer.kick(current_app._get_current_object())

    from app.services.auto_report_service import AutoReportService
    from app.services.auto_report.auto_report_history_service import AutoReportHistoryService
    from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
    from app.services.osip_report_email_service import OsipReportEmailService

    try:
        cfg = AutoReportService.get_global_config()
        sched = AutoReportService.get_schedule('AGRO', date_str)
        if ('AGRO' in cfg.get('enabled_lines', ['AGRO'])
                and (AutoReportService.is_report_day(date_str) or sched.get('is_custom'))
                and not sched.get('is_paused')
                and _is_due(now, sched.get('scheduled_time') or '15:00')
                and not AutoReportService.is_1500_report_sent('AGRO', date_str)):
            AutoReportService.send_shift1_report_at_1500(linia='AGRO', date_str=date_str)
    except Exception:
        logger.exception('Daily production report attempt failed')

    try:
        cfg = OsipEmailSettingsRepository().get_settings()
        if not (cfg.is_active and cfg.daily_report_enabled):
            return
        if not _is_due(now, cfg.daily_report_time or '15:00'):
            return
        if str(cfg.last_daily_report_date) == date_str:
            return
        # Durable reservation is shared across workers and survives restarts.
        if not AutoReportHistoryService.claim_report_execution('MAGAZYN', date_str, '15:00'):
            return
        try:
            ok, _ = OsipReportEmailService().send_daily_warehouse_summary_report(date_str=date_str, force=False)
            if ok:
                AutoReportHistoryService.mark_report_sent('MAGAZYN', date_str, '15:00', '')
            else:
                AutoReportHistoryService.mark_report_failed('MAGAZYN', date_str, '15:00', 'Automatic attempt unsuccessful; no retry')
        except Exception:
            AutoReportHistoryService.mark_report_failed('MAGAZYN', date_str, '15:00', 'Automatic attempt raised an exception; no retry')
            raise
    except Exception:
        logger.exception('Daily warehouse report attempt failed')
