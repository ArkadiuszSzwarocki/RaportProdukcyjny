"""
Fasada usług raportowania e-mail i generowania dokumentów magazynowych.
Integruje wyspecjalizowane serwisy:
- WarehouseActivityQueryService (Query / Dane)
- WarehouseDocumentClassifier (Reguły / Domeny)
- WarehouseStatusResolver (Statusy pozycji i zleceń)
- WarehousePdfReportBuilder (Generowanie PDF A4)
- WarehouseEmailTemplateBuilder (Szablony HTML e-mail)
- WarehouseReportMailer (Wysyłka SMTP)
"""
from typing import Dict, Any, List, Optional, Tuple
import os
import threading
import json
from datetime import datetime, date
from app.db import get_db_connection
from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
from app.services.warehouse_reports.warehouse_status_resolver import WarehouseStatusResolver
from app.services.warehouse_reports.warehouse_activity_query_service import WarehouseActivityQueryService
from app.services.warehouse_reports.warehouse_pdf_report_builder import WarehousePdfReportBuilder
from app.services.warehouse_reports.warehouse_email_template_builder import WarehouseEmailTemplateBuilder
from app.services.warehouse_reports.warehouse_report_mailer import WarehouseReportMailer


class OsipReportEmailService:
    _dispatch_lock = threading.Lock()
    _active_dispatches = set()
    _sent_daily_dates = set()

    def __init__(self):
        self.settings_repo = OsipEmailSettingsRepository()

    # --- DELEGOWANE METODY DOMENOWE (DLA KOMPATYBILNOŚCI) ---
    @staticmethod
    def _is_production_zone(loc: Optional[str]) -> bool:
        return WarehouseDocumentClassifier.is_production_zone(loc)

    @staticmethod
    def _is_osip_location(loc: Optional[str]) -> bool:
        return WarehouseDocumentClassifier.is_osip_location(loc)

    @staticmethod
    def _is_mp01_location(loc: Optional[str]) -> bool:
        return WarehouseDocumentClassifier.is_mp01_location(loc)

    @staticmethod
    def _is_rack_location(loc: Optional[str]) -> bool:
        return WarehouseDocumentClassifier.is_rack_location(loc)

    @classmethod
    def is_production_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        return WarehouseDocumentClassifier.is_production_movement(dostawa, items)

    @classmethod
    def is_internal_mp01_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        return WarehouseDocumentClassifier.is_internal_mp01_movement(dostawa, items)

    @classmethod
    def categorize_delivery_doc(cls, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return WarehouseDocumentClassifier.categorize_delivery_doc(dostawa, items)

    @staticmethod
    def _extract_item_qty(item: Dict[str, Any]) -> float:
        return WarehouseActivityQueryService.extract_item_qty(item)

    @classmethod
    def get_daily_warehouse_activity(cls, date_str: str) -> Dict[str, Any]:
        return WarehouseActivityQueryService.get_daily_warehouse_activity(date_str)

    @staticmethod
    def generate_delivery_pdf(dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        return WarehousePdfReportBuilder.generate_delivery_pdf(dostawa, items)

    @staticmethod
    def generate_transfer_pdf(transfer: Dict[str, Any]) -> str:
        return WarehousePdfReportBuilder.generate_transfer_pdf(transfer)

    @staticmethod
    def build_daily_summary_report_html(date_str: str, activity_data: Dict[str, Any]) -> str:
        return WarehouseEmailTemplateBuilder.build_daily_summary_report_html(date_str, activity_data)

    # --- WYSYŁKA POJEDYNCZEJ DOSTAWY / PRZESUNIĘCIA ---
    def send_central_delivery_osip_report(self, dostawa_id: Any) -> Tuple[bool, str]:
        """Wysyła raport e-mail po przyjęciu dostawy lub przesunięcia MM wraz z załącznikiem PDF."""
        dispatch_key = f"delivery_{dostawa_id}"
        with self._dispatch_lock:
            if dispatch_key in self._active_dispatches:
                return False, f"Wysyłka e-mail dla dostawy {dostawa_id} jest już w toku."
            self._active_dispatches.add(dispatch_key)

        try:
            conn = get_db_connection()
            dostawa = None
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM magazyn_dostawy WHERE id = %s", (dostawa_id,))
                dostawa = cursor.fetchone()
                cursor.close()
            finally:
                conn.close()

            if not dostawa:
                return False, f"Nie znaleziono przesunięcia/dostawy o ID: {dostawa_id}"

            if dostawa.get('email_sent_at'):
                sent_at = dostawa.get('email_sent_at')
                sent_str = sent_at.strftime('%Y-%m-%d %H:%M') if hasattr(sent_at, 'strftime') else str(sent_at)
                return False, f"Raport e-mail dla dokumentu #{dostawa_id} został już wcześniej wysłany ({sent_str})."

            try:
                items = json.loads(dostawa.get('items') or '[]')
            except Exception:
                items = []

            if self.is_production_movement(dostawa, items):
                return False, f"Dokument #{dostawa_id} dotyczy przesunięcia z produkcji — pominięto wysyłkę e-mail."
            if self.is_internal_mp01_movement(dostawa, items):
                return False, f"Dokument #{dostawa_id} dotyczy przesunięcia wewnątrz strefy MP01 — pominięto wysyłkę e-mail."

            config = self.settings_repo.get_settings()
            if not config.is_active:
                return False, "Moduł wysyłki e-mail jest wyłączony w ustawieniach."
            if not config.is_configured:
                return False, "Dedykowane konto e-mail nadawcy nie zostało jeszcze skonfigurowane."

            recipients = config.recipients_list
            if not recipients:
                return False, "Brak zdefiniowanych adresów e-mail odbiorców w Ustawieniach E-mail."

            cat = self.categorize_delivery_doc(dostawa, items)
            ref = cat['ref']
            source_val = cat['source_value']
            dest_val = cat['dest_value']
            is_external = cat['is_external']

            if is_external:
                subject = f"Dostawa WZ: {ref} ({source_val} ➔ {dest_val})"
            else:
                subject = f"Przesunięcie MM nr: {ref} ({source_val} ➔ {dest_val})"

            body_html = WarehouseEmailTemplateBuilder.build_single_delivery_html(dostawa, items)
            pdf_path = None
            try:
                pdf_path = WarehousePdfReportBuilder.generate_delivery_pdf(dostawa, items)
                pdf_filename = f"{'Dostawa_WZ' if is_external else 'Przesuniecie_MM'}_{ref}.pdf"
                attachments = [(pdf_path, pdf_filename)] if pdf_path else []

                ok, msg = WarehouseReportMailer.send_raw_email(config, recipients, subject, body_html, attachments=attachments)
                if ok:
                    conn2 = get_db_connection()
                    try:
                        cursor2 = conn2.cursor()
                        cursor2.execute(
                            "UPDATE magazyn_dostawy SET email_sent_at = NOW(), email_sent_to = %s WHERE id = %s",
                            (", ".join(recipients), dostawa_id)
                        )
                        conn2.commit()
                        cursor2.close()
                    finally:
                        conn2.close()
                    return True, f"Raport e-mail dla dokumentu {ref} został pomyślnie wysłany na adresy: {', '.join(recipients)}."
                return ok, msg
            finally:
                if pdf_path and os.path.exists(pdf_path):
                    try:
                        os.remove(pdf_path)
                    except Exception:
                        pass
        finally:
            with self._dispatch_lock:
                self._active_dispatches.discard(dispatch_key)

    # --- WYSYŁKA RAPORTU DZIENNEGO ---
    def send_daily_warehouse_summary_report(self, date_str: Optional[str] = None, force: bool = False, recipient_override: Optional[str] = None) -> Tuple[bool, str]:
        """Generuje i wysyła zbiorczy raport e-mail z podsumowaniem dnia oraz załącznikami PDF."""
        if not date_str:
            date_str = date.today().strftime('%Y-%m-%d')

        dispatch_key = f"daily_report_{date_str}"
        with self._dispatch_lock:
            if not force and not recipient_override and (date_str in self._sent_daily_dates):
                return False, f"Dzienny raport magazynowy za dzień {date_str} został już wysłany w tej sesji."
            if dispatch_key in self._active_dispatches:
                return False, f"Wysyłka dziennego raportu magazynowego za dzień {date_str} jest już w toku."
            self._active_dispatches.add(dispatch_key)

        try:
            config = self.settings_repo.get_settings()
            if not config.is_active:
                return False, "Moduł powiadomień magazynowych jest wyłączony w ustawieniach."
            if not config.is_configured:
                return False, "Serwer SMTP nie został jeszcze poprawnie skonfigurowany."

            recipients = [recipient_override.strip()] if recipient_override else config.recipients_list
            if not recipients:
                return False, "Brak zdefiniowanych adresatów w konfiguracji."

            activity_data = WarehouseActivityQueryService.get_daily_warehouse_activity(date_str)
            if not activity_data.get('has_activity'):
                return False, f"Brak ruchów magazynowych (dostaw ani przesunięć MM) w dniu {date_str}."

            body_html = WarehouseEmailTemplateBuilder.build_daily_summary_report_html(date_str, activity_data)
            subject = f"📊 Raport Dzienny — Ruch Magazynowy ({date_str}) | Dostawy i Przesunięcia MM"

            attachments = []
            temp_files_to_cleanup = []

            try:
                for doc in activity_data.get('all_documents', []):
                    doc_pdf = None
                    if doc.get('raw_dostawa'):
                        doc_pdf = WarehousePdfReportBuilder.generate_delivery_pdf(doc['raw_dostawa'], doc.get('raw_items', []))
                    elif doc.get('raw_transfer'):
                        tr_dict = dict(doc['raw_transfer'])
                        tr_dict['items'] = doc.get('raw_items', [])
                        doc_pdf = WarehousePdfReportBuilder.generate_transfer_pdf(tr_dict)

                    if doc_pdf and os.path.exists(doc_pdf):
                        temp_files_to_cleanup.append(doc_pdf)
                        display_name = doc.get('pdf_filename') or os.path.basename(doc_pdf)
                        attachments.append((doc_pdf, display_name))

                ok, msg = WarehouseReportMailer.send_raw_email(config, recipients, subject, body_html, attachments=attachments)
                if ok:
                    if not recipient_override:
                        with self._dispatch_lock:
                            self._sent_daily_dates.add(date_str)
                        try:
                            self.settings_repo.update_last_daily_report_date(date_str)
                        except Exception as db_err:
                            print(f"[DAILY_REPORT_EMAIL] Ostrzeżenie zapisu last_daily_report_date w bazie: {db_err}")
                    return True, f"Zbiorczy raport dzienny za dzień {date_str} (z {len(attachments)} załącznikami PDF do druku) wysłany pomyślnie na adresy: {', '.join(recipients)}."
                return ok, msg
            finally:
                for fpath in temp_files_to_cleanup:
                    if fpath and os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass
        finally:
            with self._dispatch_lock:
                self._active_dispatches.discard(dispatch_key)

    # --- ASYNCHRONICZNE TRIGGERY DLA DAEMONA I ROUTINGU ---
    @classmethod
    def trigger_async_daily_warehouse_report(cls, date_str: Optional[str] = None, force: bool = False) -> None:
        def _worker():
            try:
                service = cls()
                ok, msg = service.send_daily_warehouse_summary_report(date_str=date_str, force=force)
                print(f"[DAILY_REPORT_EMAIL] Wynik raportu dziennego ({date_str}): {msg}")
            except Exception as ex:
                print(f"[DAILY_REPORT_EMAIL] Błąd krytyczny wysyłki raportu dziennego: {ex}")

        threading.Thread(target=_worker, daemon=True).start()

    @classmethod
    def trigger_async_delivery_report(cls, dostawa_id: Any) -> None:
        if not dostawa_id:
            return
        def _worker():
            try:
                service = cls()
                ok, msg = service.send_central_delivery_osip_report(dostawa_id)
                print(f"[WAREHOUSE_EMAIL] Wynik wysyłki dla dostawy {dostawa_id}: {msg}")
            except Exception as ex:
                print(f"[WAREHOUSE_EMAIL] Błąd wysyłki dla dostawy {dostawa_id}: {ex}")

        threading.Thread(target=_worker, daemon=True).start()
