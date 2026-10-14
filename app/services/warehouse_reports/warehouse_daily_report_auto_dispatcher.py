"""
Orchestrates the automatic daily warehouse report: schedule check, history tracking and retry backoff.
"""
import logging
import time
from typing import Any, Optional, Tuple

from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService
from app.services.osip_report_email_service import OsipReportEmailService

logger = logging.getLogger(__name__)


class WarehouseDailyReportAutoDispatcher:
    """Sends the daily warehouse report once per day and records every attempt in auto_report_history.

    Retry backoff is delegated to AutoReportHistoryService.claim_report_execution, which blocks a
    new attempt for a day/type while the previous FAILED attempt is younger than its cooldown.
    """

    HISTORY_LINE = 'MAGAZYN'
    HISTORY_TYPE = 'DZIENNY'
    CHECK_INTERVAL_SECONDS = 60.0

    def __init__(self, settings_repo: Optional[Any] = None, history_service: Optional[Any] = None):
        self._settings_repo = settings_repo or OsipEmailSettingsRepository()
        self._history = history_service or AutoReportHistoryService
        self._completed_date: Optional[str] = None
        self._last_check_ts = 0.0

    @staticmethod
    def _normalize_time(raw_time: Optional[str]) -> str:
        value = (raw_time or '15:00').strip()
        return f"{value}:00" if len(value) == 5 else value

    def dispatch_if_due(self, today_str: str, now_time_str: str) -> Optional[Tuple[bool, str]]:
        """Runs one scheduling pass. Returns None when nothing was attempted, otherwise the attempt result."""
        if self._completed_date == today_str:
            return None

        now_ts = time.monotonic()
        if now_ts - self._last_check_ts < self.CHECK_INTERVAL_SECONDS:
            return None
        self._last_check_ts = now_ts

        config = self._settings_repo.get_settings()
        if not config.is_active or not config.daily_report_enabled:
            return None
        if now_time_str < self._normalize_time(config.daily_report_time):
            return None

        if config.last_daily_report_date == today_str or self._history.is_report_sent(
            self.HISTORY_LINE, today_str, self.HISTORY_TYPE
        ):
            self._completed_date = today_str
            return None

        if not self._history.claim_report_execution(self.HISTORY_LINE, today_str, self.HISTORY_TYPE):
            return None

        try:
            service = OsipReportEmailService(self._settings_repo)
            success, message = service.send_daily_warehouse_summary_report(date_str=today_str, force=False)
        except Exception as exc:
            logger.exception("[WAREHOUSE_DAILY_REPORT] Unexpected error while sending report for %s", today_str)
            success, message = False, f"Błąd krytyczny wysyłki: {exc}"

        if success:
            recipients = ", ".join(config.recipients_list) or message
            self._history.mark_report_sent(self.HISTORY_LINE, today_str, self.HISTORY_TYPE, recipients)
            self._completed_date = today_str
        else:
            self._history.mark_report_failed(self.HISTORY_LINE, today_str, self.HISTORY_TYPE, message)

        return success, message
