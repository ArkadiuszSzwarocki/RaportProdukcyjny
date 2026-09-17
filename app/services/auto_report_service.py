"""
Serwis automatycznego raportowania (AutoReportService).
Czysta fasada integrująca wyspecjalizowane serwisy domeny auto_report:
- AutoReportScheduleService (harmonogram i odraczanie)
- AutoReportConfigService (dni tygodnia i linie)
- AutoReportHistoryService (historia i atomowa rezerwacja)
- AutoReportActivityDetector (detekcja produkcji i pracy po 15:00)
- AutoReportRecipientsService (odbiorcy e-mail)
- AutoReportDispatcherService (generowanie i wysyłka raportów)
"""
from typing import Tuple, List, Optional, Dict, Any, Union
from datetime import datetime, date

from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService
from app.services.auto_report.auto_report_config_service import AutoReportConfigService
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService
from app.services.auto_report.auto_report_activity_detector import AutoReportActivityDetector
from app.services.auto_report.auto_report_recipients_service import AutoReportRecipientsService
from app.services.auto_report.auto_report_dispatcher_service import AutoReportDispatcherService


class AutoReportService:
    """Zarządza automatycznym generowaniem i wysyłką raportów o 15:00 oraz po 15:00."""

    @staticmethod
    def _ensure_history_table(conn):
        return AutoReportHistoryService.ensure_history_tables(conn)

    @classmethod
    def get_schedule(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> Dict[str, Any]:
        return AutoReportScheduleService.get_schedule(linia, date_str)

    @classmethod
    def set_schedule(cls, linia: str, date_str: str, scheduled_time: str, is_paused: bool = False, user_name: str = 'Lider') -> Tuple[bool, str]:
        return AutoReportScheduleService.set_schedule(linia, date_str, scheduled_time, is_paused, user_name)

    @classmethod
    def postpone_report(cls, linia: str = 'AGRO', date_str: Optional[str] = None,
                        add_minutes: Optional[int] = None, new_time: Optional[str] = None,
                        pause_completely: bool = False, reset_to_default: bool = False,
                        user_name: str = 'Lider') -> Tuple[bool, str, Dict[str, Any]]:
        return AutoReportScheduleService.postpone_report(
            linia=linia,
            date_str=date_str,
            add_minutes=add_minutes,
            new_time=new_time,
            pause_completely=pause_completely,
            reset_to_default=reset_to_default,
            user_name=user_name
        )

    @staticmethod
    def get_default_recipients(linia: str = 'AGRO') -> List[str]:
        return AutoReportRecipientsService.get_default_recipients(linia)

    @classmethod
    def is_report_sent(cls, linia: str, date_str: str, typ_raportu: str = '15:00') -> bool:
        return AutoReportHistoryService.is_report_sent(linia, date_str, typ_raportu)

    @classmethod
    def is_1500_report_sent(cls, linia: str, date_str: str) -> bool:
        return AutoReportHistoryService.is_report_sent(linia, date_str, '15:00')

    @classmethod
    def claim_report_execution(cls, linia: str, date_str: str, typ_raportu: str = '15:00') -> bool:
        return AutoReportHistoryService.claim_report_execution(linia, date_str, typ_raportu)

    @classmethod
    def mark_report_sent(cls, linia: str, date_str: str, typ_raportu: str, recipients_str: str):
        return AutoReportHistoryService.mark_report_sent(linia, date_str, typ_raportu, recipients_str)

    @classmethod
    def mark_report_failed(cls, linia: str, date_str: str, typ_raportu: str, error_msg: str):
        return AutoReportHistoryService.mark_report_failed(linia, date_str, typ_raportu, error_msg)

    @classmethod
    def mark_report_skipped_empty(cls, linia: str, date_str: str, typ_raportu: str, reason: str = 'Brak danych produkcyjnych'):
        return AutoReportHistoryService.mark_report_skipped_empty(linia, date_str, typ_raportu, reason)

    @classmethod
    def has_report_data(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> bool:
        return AutoReportActivityDetector.has_report_data(linia, date_str)

    @classmethod
    def has_activity_after_1500(cls, linia: str = 'AGRO', date_str: Optional[str] = None) -> bool:
        return AutoReportActivityDetector.has_activity_after_1500(linia, date_str)

    @classmethod
    def get_global_config(cls) -> Dict[str, Any]:
        return AutoReportConfigService.get_global_config()

    @classmethod
    def save_global_config(cls, active_days: List[int], enabled_lines: List[str], user_name: str = 'Admin') -> Tuple[bool, str]:
        return AutoReportConfigService.save_global_config(active_days, enabled_lines, user_name)

    @classmethod
    def is_line_enabled(cls, linia: str) -> bool:
        return AutoReportConfigService.is_line_enabled(linia)

    @classmethod
    def is_report_day(cls, target_date: Optional[Union[str, date, datetime]] = None) -> bool:
        return AutoReportConfigService.is_report_day(target_date)

    @classmethod
    def is_weekday(cls, target_date: Optional[Union[str, date, datetime]] = None) -> bool:
        return AutoReportConfigService.is_report_day(target_date)

    @classmethod
    def send_shift1_report_at_1500(cls, linia: str = 'AGRO', date_str: Optional[str] = None, force: bool = False) -> Tuple[bool, str]:
        return AutoReportDispatcherService.send_shift1_report_at_1500(linia, date_str, force=force)

    @classmethod
    def generate_and_send_post_1500_report(cls, linia: str = 'AGRO', date_str: Optional[str] = None, to_emails: Optional[List[str]] = None) -> Tuple[bool, str]:
        return AutoReportDispatcherService.generate_and_send_post_1500_report(linia, date_str, to_emails=to_emails)
