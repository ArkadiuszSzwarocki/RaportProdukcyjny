"""
Moduł odpowiedzialny za orkiestrację generowania plików raportowych i wysyłkę e-mail dla zmian produkcyjnych.
"""
import os
import logging
from datetime import date
from typing import Tuple, List, Optional

from app.core.database import get_db_connection
from app.core.audit import audit_log
from app.services.email_service import EmailService
from app.services.email_report_builder import EmailReportBuilder
from app.repositories.downtime_repository import DowntimeRepository
from app.services.auto_report.auto_report_config_service import AutoReportConfigService
from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService
from app.services.auto_report.auto_report_activity_detector import AutoReportActivityDetector
from app.services.auto_report.auto_report_recipients_service import AutoReportRecipientsService
from app.services.shift_close_service import get_shift_actual_production

logger = logging.getLogger(__name__)


class AutoReportDispatcherService:
    @classmethod
    def send_shift1_report_at_1500(cls, linia: str = 'AGRO', date_str: Optional[str] = None, force: bool = False) -> Tuple[bool, str]:
        """Generuje i wysyła automatyczny raport o 15:00 dla I zmiany (zgodnie z konfiguracją linii i dni)."""
        if not date_str:
            date_str = str(date.today())

        if not force and linia.strip().upper() != 'AGRO':
            msg = f"Automatyczny raport o 15:00 dla linii {linia} jest wyłączony — wysyłane są wyłącznie raporty AGRO."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            return True, msg

        if not force and not AutoReportConfigService.is_line_enabled(linia):
            msg = f"Automatyczny raport dla linii {linia} jest wyłączony w konfiguracji."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            return True, msg

        if not force:
            sched = AutoReportScheduleService.get_schedule(linia, date_str)
            is_custom_sched = sched.get('is_custom', False)
            if not is_custom_sched and not AutoReportConfigService.is_report_day(date_str):
                msg = f"Automatyczny raport dla {linia} w dniu {date_str} pominięty - dzień nie jest aktywny w harmonogramie wysyłek."
                logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
                return True, msg

            if sched.get('is_paused'):
                msg = f"Automatyczny raport dla {linia} w dniu {date_str} jest wstrzymany (is_paused=True)."
                logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
                return True, msg

        if AutoReportHistoryService.is_report_sent(linia, date_str, '15:00'):
            msg = f"Raport o 15:00 dla {linia} w dniu {date_str} został już wysłany."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            return True, msg

        if not force and not AutoReportActivityDetector.has_report_data(linia, date_str):
            msg = f"Automatyczny raport o 15:00 dla linii {linia} w dniu {date_str} pominięty — raport nie zawiera żadnych danych produkcyjnych ani przestojów."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            AutoReportHistoryService.mark_report_skipped_empty(linia, date_str, '15:00', msg)
            return True, msg

        to_emails = AutoReportRecipientsService.get_default_recipients(linia)
        if not to_emails:
            msg = f"Brak skonfigurowanych odbiorców e-mail dla linii {linia}. Anulowano wysyłkę o 15:00."
            logger.warning("[AUTO_REPORT_DISPATCHER] %s", msg)
            if not force:
                AutoReportHistoryService.mark_report_failed(linia, date_str, '15:00', msg)
            return False, msg

        if not force and not AutoReportHistoryService.claim_report_execution(linia, date_str, '15:00'):
            msg = f"Raport o 15:00 dla {linia} w dniu {date_str} jest już wysłany, w trakcie wysyłki lub w okresie cooldownu."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            return True, msg

        logger.info("[AUTO_REPORT_DISPATCHER] Rozpoczynam generowanie raportu o 15:00 dla linii %s (odbiorcy: %s)", linia, to_emails)

        try:
            from app.services.shift_close_service import _load_shift_notes, _generate_report_files

            uwagi = _load_shift_notes(date_str, linia=linia)
            lider_name = "System Auto-Raport (I Zmiana)"
            xls_path, txt_path, pdf_path = _generate_report_files(date_str, uwagi, lider_name, linia=linia)

            valid_attachments = [str(p) for p in [pdf_path, xls_path] if p and os.path.exists(p)]
            att_filenames = [os.path.basename(p) for p in valid_attachments]

            prod_data = get_shift_actual_production(date_str, linia=linia)
            suma_zasyp = prod_data['suma_zasyp']
            suma_workowanie = prod_data['suma_workowanie']
            palety_count = prod_data['palety_count']

            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            total_downtime_min = sum(int(dt.get('czas_trwania_min') or 0) for dt in downtimes)

            sched = AutoReportScheduleService.get_schedule(linia, date_str)
            sched_time_display = sched.get('scheduled_time') or '15:00'

            body_html = EmailReportBuilder.build_shift_report_html(
                linia=linia,
                date_str=date_str,
                lider_name=f"Automatyczny Raport I Zmiany (godz. {sched_time_display})",
                suma_zasyp=suma_zasyp,
                suma_workowanie=suma_workowanie,
                downtimes=downtimes,
                total_downtime_min=total_downtime_min,
                notes_text=uwagi,
                attachments_names=att_filenames,
                palety_count=palety_count
            )

            subject = f"📊 Raport Produkcyjny {linia} — I Zmiana ({sched_time_display}) — {date_str}"

            email_service = EmailService()
            success, message = email_service.send_report_email(
                to_emails=to_emails,
                subject=subject,
                body_html=body_html,
                attachments=valid_attachments
            )

            if success:
                AutoReportHistoryService.mark_report_sent(linia, date_str, '15:00', ", ".join(to_emails))
                audit_log(
                    'Automatyczna wysyłka raportu o 15:00',
                    f'Linia={linia}, Data={date_str}, Odbiorcy={", ".join(to_emails)}'
                )
                logger.info("[AUTO_REPORT_DISPATCHER] Raport o 15:00 wysłany pomyślnie na %s", to_emails)
                return True, f"Raport o 15:00 wysłany pomyślnie do {len(to_emails)} odbiorców."
            else:
                AutoReportHistoryService.mark_report_failed(linia, date_str, '15:00', message)
                logger.error("[AUTO_REPORT_DISPATCHER] Błąd wysyłki e-mail o 15:00: %s", message)
                return False, message
        except Exception as e:
            AutoReportHistoryService.mark_report_failed(linia, date_str, '15:00', str(e))
            logger.exception("[AUTO_REPORT_DISPATCHER] Wyjątek podczas generowania raportu o 15:00: %s", e)
            return False, str(e)

    @classmethod
    def generate_and_send_post_1500_report(cls, linia: str = 'AGRO', date_str: Optional[str] = None, to_emails: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Tworzy i wysyła nowy dedykowany raport dla pracy po godz. 15:00 (II zmiana / nadgodziny)."""
        if not date_str:
            date_str = str(date.today())

        if not to_emails:
            to_emails = AutoReportRecipientsService.get_default_recipients(linia)

        if not to_emails:
            return False, "Brak odbiorców e-mail dla raportu po 15:00."

        if not AutoReportActivityDetector.has_report_data(linia, date_str):
            msg = f"Raport po 15:00 dla linii {linia} w dniu {date_str} pominięty — raport nie zawiera żadnych danych produkcyjnych ani przestojów."
            logger.info("[AUTO_REPORT_DISPATCHER] %s", msg)
            AutoReportHistoryService.mark_report_skipped_empty(linia, date_str, 'po_15:00', msg)
            return True, msg

        if not AutoReportHistoryService.claim_report_execution(linia, date_str, 'po_15:00'):
            return True, f"Raport po 15:00 dla {linia} w dniu {date_str} jest już wysłany, w trakcie wysyłki lub w okresie cooldownu."

        try:
            from app.services.shift_close_service import _load_shift_notes, _generate_report_files

            uwagi = _load_shift_notes(date_str, linia=linia)
            lider_name = "Raport Popołudniowy / II Zmiana (po 15:00)"

            xls_path, txt_path, pdf_path = _generate_report_files(
                date_str=date_str,
                uwagi=uwagi,
                lider_name=lider_name,
                linia=linia
            )

            valid_attachments = [str(p) for p in [pdf_path, xls_path] if p and os.path.exists(p)]
            att_filenames = [os.path.basename(p) for p in valid_attachments]

            prod_data = get_shift_actual_production(date_str, linia=linia)
            suma_zasyp = prod_data['suma_zasyp']
            suma_workowanie = prod_data['suma_workowanie']
            palety_count = prod_data['palety_count']

            downtimes = DowntimeRepository().get_downtimes(linia, date_str, date_str)
            total_downtime_min = sum(int(dt.get('czas_trwania_min') or 0) for dt in downtimes)

            body_html = EmailReportBuilder.build_shift_report_html(
                linia=linia,
                date_str=date_str,
                lider_name="Raport Popołudniowy / II Zmiana (po godz. 15:00)",
                suma_zasyp=suma_zasyp,
                suma_workowanie=suma_workowanie,
                downtimes=downtimes,
                total_downtime_min=total_downtime_min,
                notes_text=uwagi,
                attachments_names=att_filenames,
                palety_count=palety_count
            )

            subject = f"📊 Raport Produkcyjny {linia} — Praca po 15:00 / II Zmiana — {date_str}"

            email_service = EmailService()
            success, message = email_service.send_report_email(
                to_emails=to_emails,
                subject=subject,
                body_html=body_html,
                attachments=valid_attachments
            )

            if success:
                AutoReportHistoryService.mark_report_sent(linia, date_str, 'po_15:00', ", ".join(to_emails))
                audit_log(
                    'Wysyłka raportu popołudniowego po 15:00',
                    f'Linia={linia}, Data={date_str}, Odbiorcy={", ".join(to_emails)}'
                )
                logger.info("[AUTO_REPORT_DISPATCHER] Raport po 15:00 wysłany pomyślnie na %s", to_emails)
                return True, "Raport popołudniowy (po 15:00) został pomyślnie wygenerowany i wysłany."
            else:
                AutoReportHistoryService.mark_report_failed(linia, date_str, 'po_15:00', message)
                return False, message
        except Exception as e:
            AutoReportHistoryService.mark_report_failed(linia, date_str, 'po_15:00', str(e))
            logger.exception("[AUTO_REPORT_DISPATCHER] Błąd generowania raportu po 15:00: %s", e)
            return False, str(e)
