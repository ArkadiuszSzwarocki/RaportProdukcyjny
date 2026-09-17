"""
Serwis do wysyłania raportów e-mail po przyjęciu dostaw, przesunięć MM oraz transferów OSIP.
Wysyła czytelne raporty HTML wraz z załącznikiem PDF (A4 do druku) z dedykowanego konta SMTP.
Rozróżnia typy dokumentów:
- Dostawa Centrala
- Dostawa OSIP
- Przesunięcie MM
- Transfer: [Skąd] ➔ [Dokąd]
Zawiera jednoznaczne informacje o tym Kto otworzył i Kto przyjął dokument.
"""
import smtplib
import os
import re
import json
import tempfile
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Tuple, Dict, Any, Set
from datetime import datetime

from app.core.database import get_db_connection
from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
from app.models.osip_email_settings_model import OsipEmailSettingsModel


class OsipReportEmailService:
    """Obsługa wysyłki raportów dostaw, przesunięć MM i transferów z dedykowanego konta pocztowego."""

    OSIP_LOCATION_KEYWORDS = ('OSIP', 'OS01', 'OS02', 'OS03', 'OS04', 'OS05', 'OS06', 'OS07', 'OS08', 'OS09', 'W_TRANZYCIE_OSIP')
    ALLOWED_CENTRAL_WAREHOUSE_LOCATIONS = (
        'MP01', 'MPO1',
        'BFMP01', 'BF_MP01',
        'BFMS01', 'BF_MS01',
        'MS01',
        'PSD', 'PSD01',
        'MGW01', 'MGW02',
        'MOP01', 'MO01',
        'MDO01', 'MD01', 'MDM01'
    )
    
    _active_dispatches: Set[str] = set()
    _sent_daily_dates: Set[str] = set()
    _dispatch_lock: threading.Lock = threading.Lock()

    def __init__(self, settings_repo: Optional[OsipEmailSettingsRepository] = None):
        self.settings_repo = settings_repo or OsipEmailSettingsRepository()

    @classmethod
    def is_allowed_central_warehouse_location(cls, loc: Optional[str]) -> bool:
        """
        Sprawdza czy lokalizacja należy do ściśle dozwolonych stref Magazynu Centralnego:
        - regały: R + cyfry (np. R010101, R020102, R090103 itp.), RR + cyfry, lub 4-8 cyfr (np. 010102)
        - bufory i strefy: MP01, BFMP01 (BF_MP01), BFMS01 (BF_MS01), MS01, PSD, PSD01, MGW01, MGW02, MOP01, MDO01 (MD01, MDM01)
        """
        if not loc:
            return False
        clean_raw = str(loc).strip()
        if not clean_raw:
            return False
        parts = [p.strip() for p in re.split(r'[,;/|]+', clean_raw) if p.strip()]
        for p in parts:
            clean = re.sub(r'[^A-Z0-9]', '', p.upper())
            if not clean:
                continue
            if re.match(r'^RR?\d{1,8}$', clean) or re.match(r'^\d{4,8}$', clean) or re.match(r'^REGAL\d{1,8}$', clean):
                return True
            clean_allowed = {re.sub(r'[^A-Z0-9]', '', z) for z in cls.ALLOWED_CENTRAL_WAREHOUSE_LOCATIONS}
            if clean in clean_allowed:
                return True
        return False

    @classmethod
    def is_allowed_central_transfer(cls, source: Optional[str], target: Optional[str]) -> bool:
        """
        Sprawdza czy przesunięcie odbywa się wyłącznie w obrębie dozwolonych lokalizacji Magazynu Centralnego.
        Dozwolone są regały oraz bufory: MP01, BFMP01, BFMS01, MS01, PSD, PSD01, MGW01, MGW02, MOP01, MDO01.
        Wyklucza ruchy z/do OSIP, produkcji (BB, MZ, KO itp.) oraz innych nieautoryzowanych stref.
        """
        src_clean = str(source or '').strip()
        tgt_clean = str(target or '').strip()

        if not src_clean and not tgt_clean:
            return False

        if cls.is_osip_involved(src_clean, tgt_clean):
            return False

        src_allowed = cls.is_allowed_central_warehouse_location(src_clean)
        tgt_allowed = cls.is_allowed_central_warehouse_location(tgt_clean)

        neutral_keywords = {'WIELE', 'MAGAZYN', 'CENTRALA', 'MAGAZYNCENTRALNY', 'CENTRALNY', ''}
        src_norm = re.sub(r'[^A-Z0-9]', '', src_clean.upper())
        tgt_norm = re.sub(r'[^A-Z0-9]', '', tgt_clean.upper())

        if src_allowed and tgt_allowed:
            return True
        if src_allowed and (tgt_norm in neutral_keywords or not tgt_clean):
            return True
        if tgt_allowed and (src_norm in neutral_keywords or not src_clean):
            return True

        return False

    @classmethod
    def _is_osip_location(cls, loc: Optional[str]) -> bool:
        """Sprawdza pojedynczą lokalizację pod kątem przynależności do magazynu OSIP."""
        if not loc:
            return False
        loc_upper = str(loc).strip().upper()
        if any(keyword in loc_upper for keyword in cls.OSIP_LOCATION_KEYWORDS):
            return True
        if loc_upper.startswith('OS'):
            return True
        return False

    @classmethod
    def is_osip_involved(
        cls,
        source: Optional[str] = None,
        destination: Optional[str] = None,
        items: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Sprawdza czy operacja magazynowa dotyczy magazynu OSIP (ruch DO OSIP lub Z OSIP)."""
        if cls._is_osip_location(source) or cls._is_osip_location(destination):
            return True

        if items and isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                target_loc = str(it.get('lokalizacja_przyjecia') or it.get('targetSpot') or it.get('lokalizacja_do') or '').strip().upper()
                source_loc = str(it.get('sourceSpot') or it.get('lokalizacja_z') or '').strip().upper()
                if cls._is_osip_location(target_loc) or cls._is_osip_location(source_loc):
                    return True

        return False

    @classmethod
    def is_destination_osip(cls, destination: Optional[str], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Kompatybilność wsteczna: sprawdza powiązanie z OSIP."""
        return cls.is_osip_involved(None, destination, items)

    @classmethod
    def categorize_delivery_doc(cls, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Rozpoznaje szczegółowy typ i metadane dokumentu magazynowego:
        - Dostawa Centrala
        - Dostawa OSIP
        - Przesunięcie MM
        """
        supplier = (dostawa.get('supplier') or '').strip()
        source_loc = (dostawa.get('lokalizacja_z') or '').strip()
        dest_loc = (dostawa.get('lokalizacja_do') or '').strip()
        ref = dostawa.get('order_ref') or f"#{dostawa.get('id')}"

        has_supplier = bool(supplier) and supplier not in ('-', 'None', '')
        is_external = has_supplier

        # Dynamicznie pobierz rzeczywiste lokalizacje docelowe z przyjętych pozycji
        actual_target_spots = sorted({
            (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip()
            for it in items
            if (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip() and (it.get('lokalizacja_przyjecia') or it.get('targetSpot') or '').strip() != 'OCZEKUJĄCE'
        })
        if (not dest_loc or dest_loc == 'OCZEKUJĄCE') and actual_target_spots:
            dest_loc = ", ".join(actual_target_spots)

        # Dynamicznie pobierz rzeczywiste lokalizacje źródłowe jeśli brak w nagłówku
        if not source_loc:
            actual_source_spots = sorted({
                (it.get('sourceSpot') or it.get('source_location') or '').strip()
                for it in items
                if (it.get('sourceSpot') or it.get('source_location') or '').strip()
            })
            if actual_source_spots:
                source_loc = ", ".join(actual_source_spots)

        is_dest_osip = cls._is_osip_location(dest_loc) or any(cls._is_osip_location(it.get('lokalizacja_przyjecia') or it.get('targetSpot')) for it in items)
        is_source_osip = cls._is_osip_location(source_loc)

        if is_external:
            if is_dest_osip:
                doc_type_code = 'DOSTAWA_OSIP'
                doc_title = 'Dostawa OSIP'
                header_title = '📦 Raport Przyjęcia: Dostawa OSIP'
                subject_tag = 'Dostawa OSIP'
            else:
                doc_type_code = 'DOSTAWA_CENTRALA'
                doc_title = 'Dostawa Centrala'
                header_title = '📦 Raport Przyjęcia: Dostawa Centrala'
                subject_tag = 'Dostawa Centrala'
            theme_color_from = '#1e3a8a'
            theme_color_to = '#2563eb'
            source_label = 'DOSTAWCA'
            source_value = supplier or 'Dostawca zewnętrzny'
            dest_label = 'LOKALIZACJA DOCELOWA'
            dest_value = dest_loc or 'Magazyn'
            creator_label = 'OTWORZYŁ / WPROWADZIŁ'
            acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
        else:
            doc_type_code = 'PRZESUNIECIE_MM'
            doc_title = 'Przesunięcie MM'
            header_title = '🔄 Raport Realizacji: Przesunięcie MM'
            theme_color_from = '#065f46'
            theme_color_to = '#059669'
            source_label = 'LOKALIZACJA ŹRÓDŁOWA (SKĄD)'
            source_value = source_loc or 'Magazyn'
            dest_label = 'LOKALIZACJA DOCELOWA (DOKĄD)'
            dest_value = dest_loc or 'Magazyn'
            creator_label = 'WYDAŁ / OTWORZYŁ'
            acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
            subject_tag = 'Przesunięcie MM'

        created_by = dostawa.get('created_by') or 'System'
        created_at = dostawa.get('created_at')
        created_str = created_at.strftime('%Y-%m-%d %H:%M') if hasattr(created_at, 'strftime') else str(created_at or '-')

        accepted_by = (
            dostawa.get('potwierdzone_przez') or
            next((it.get('accepted_by') for it in items if it.get('accepted_by')), None) or
            dostawa.get('updated_by') or
            '-'
        )
        accepted_at = (
            dostawa.get('potwierdzone_at') or
            next((it.get('accepted_at') for it in items if it.get('accepted_at')), None) or
            dostawa.get('updated_at') or
            created_at
        )
        accepted_str = accepted_at.strftime('%Y-%m-%d %H:%M') if hasattr(accepted_at, 'strftime') else (str(accepted_at) if accepted_at else '-')

        return {
            'doc_type_code': doc_type_code,
            'doc_title': doc_title,
            'header_title': header_title,
            'theme_color_from': theme_color_from,
            'theme_color_to': theme_color_to,
            'source_label': source_label,
            'source_value': source_value,
            'dest_label': dest_label,
            'dest_value': dest_value,
            'creator_label': creator_label,
            'creator_value': f"{created_by} ({created_str})",
            'created_by': created_by,
            'created_str': created_str,
            'acceptor_label': acceptor_label,
            'acceptor_value': f"{accepted_by} ({accepted_str})" if accepted_by != '-' else '-',
            'accepted_by': accepted_by,
            'accepted_str': accepted_str,
            'subject_tag': subject_tag,
            'ref': ref,
            'is_external': is_external,
            'is_osip': is_dest_osip or is_source_osip
        }

    def test_smtp_connection(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: str,
        smtp_password: str
    ) -> Tuple[bool, str]:
        """Testuje połączenie i autoryzację na dedykowanym serwerze SMTP."""
        server = None
        try:
            smtp_server = (smtp_server or '').strip()
            smtp_port = int(smtp_port) if smtp_port else 465
            smtp_security = (smtp_security or 'SSL').strip().upper()
            smtp_username = (smtp_username or '').strip()
            smtp_password = (smtp_password or '').strip()

            if not smtp_server or not smtp_username or not smtp_password:
                return False, "Podaj serwer SMTP, login/adres e-mail oraz hasło konta nadawcy."

            if smtp_security == 'SSL' or smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=12)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=12)
                server.ehlo()
                if smtp_security == 'TLS' or smtp_port == 587:
                    server.starttls()
                    server.ehlo()

            server.login(smtp_username, smtp_password)
            server.quit()
            return True, "Połączenie z dedykowanym serwerem SMTP oraz autoryzacja powiodły się!"
        except smtplib.SMTPAuthenticationError:
            return False, "Błąd autoryzacji SMTP: Nieprawidłowy login lub hasło skrzynki nadawcy."
        except smtplib.SMTPConnectError:
            return False, f"Błąd połączenia: Nie można połączyć się z serwerem {smtp_server}:{smtp_port}."
        except Exception as e:
            return False, f"Błąd połączenia z serwerem SMTP: {str(e)}"

    def _send_raw_email(
        self,
        config: OsipEmailSettingsModel,
        to_emails: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Wysyła e-mail przez dedykowane konto SMTP."""
        if not to_emails:
            return False, "Brak zdefiniowanych odbiorców e-mail dla raportów."

        if not config.is_configured:
            return False, "Brak skonfigurowanego dedykowanego konta e-mail nadawcy. Skonfiguruj je w Ustawieniach E-mail."

        server = None
        try:
            msg = MIMEMultipart()
            sender_str = f"{config.sender_name} <{config.smtp_username}>" if config.sender_name else config.smtp_username
            msg['From'] = sender_str
            msg['To'] = ", ".join(to_emails)
            msg['Subject'] = subject

            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            if attachments:
                for att in attachments:
                    if isinstance(att, tuple) and len(att) == 2:
                        file_path, filename = att
                    else:
                        file_path = att
                        filename = os.path.basename(file_path) if file_path else "zalacznik.pdf"
                    if file_path and os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            subtype = 'pdf' if filename.lower().endswith('.pdf') else 'octet-stream'
                            part = MIMEBase('application', subtype)
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', 'attachment', filename=filename)
                        msg.attach(part)

            if config.smtp_security == 'SSL' or config.smtp_port == 465:
                server = smtplib.SMTP_SSL(config.smtp_server, config.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(config.smtp_server, config.smtp_port, timeout=15)
                server.ehlo()
                if config.smtp_security == 'TLS' or config.smtp_port == 587:
                    server.starttls()
                    server.ehlo()

            server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.smtp_username, to_emails, msg.as_string())
            server.quit()

            try:
                from app.services.email_log_service import EmailLogService
                EmailLogService.log_email_attempt(
                    sender=config.smtp_username,
                    recipients=to_emails,
                    subject=subject,
                    source='Magazyn OSIP',
                    linia='OSIP',
                    success=True,
                    attachments=attachments
                )
            except Exception:
                pass

            return True, f"Raport przyjęcia wysłany pomyślnie na adresy: {', '.join(to_emails)} (z konta {config.smtp_username})."
        except Exception as e:
            try:
                from app.services.email_log_service import EmailLogService
                EmailLogService.log_email_attempt(
                    sender=config.smtp_username if config else 'osip_system',
                    recipients=to_emails,
                    subject=subject,
                    source='Magazyn OSIP',
                    linia='OSIP',
                    success=False,
                    error_message=str(e),
                    attachments=attachments
                )
            except Exception:
                pass

            return False, f"Błąd wysyłania e-maila: {str(e)}"

    def _render_html_to_temp_pdf(self, html_content: str, prefix: str = "raport_") -> Optional[str]:
        """Renderuje treść HTML do tymczasowego pliku PDF za pomocą Playwright."""
        safe_prefix = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in prefix)[:30]
        fd, pdf_path = tempfile.mkstemp(suffix=".pdf", prefix=safe_prefix)
        os.close(fd)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-proxy-server'])
                page = browser.new_page()
                page.set_content(html_content, wait_until="load")
                page.pdf(
                    path=pdf_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"}
                )
                browser.close()
            return pdf_path
        except Exception as e:
            print(f"[PDF_GENERATOR] Błąd generowania PDF Playwright: {e}")
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except Exception:
                    pass
            return None

    def build_transfer_report_html(self, transfer: Any) -> str:
        """Buduje raport HTML po przyjęciu Transferu Wewnętrznego OSIP."""
        code = getattr(transfer, 'transfer_code', '') or f"TR-{getattr(transfer, 'id', '')}"
        source = getattr(transfer, 'source_warehouse', '') or 'Centrala'
        dest = getattr(transfer, 'destination_warehouse', '') or 'OSIP'
        created_by = getattr(transfer, 'created_by', '') or getattr(transfer, 'dispatched_by', '') or 'System'
        completed_by = getattr(transfer, 'completed_by', None) or getattr(transfer, 'updated_by', None) or '-'
        
        created_at = getattr(transfer, 'created_at', None)
        completed_at = getattr(transfer, 'completed_at', None) or getattr(transfer, 'updated_at', None) or created_at
        
        created_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at and hasattr(created_at, 'strftime') else (str(created_at) if created_at else '-')
        completed_str = completed_at.strftime('%Y-%m-%d %H:%M') if completed_at and hasattr(completed_at, 'strftime') else (str(completed_at) if completed_at else '-')
        
        status = getattr(transfer, 'status', 'COMPLETED')
        notes = getattr(transfer, 'notes', '') or '-'

        raw_items = getattr(transfer, 'items', []) or []
        items = raw_items if isinstance(raw_items, list) else []

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        summary_products = {}
        for idx, it in enumerate(items, start=1):
            prod = getattr(it, 'product_name', None) or (it.get('product_name') if isinstance(it, dict) else 'Brak nazwy')
            nr_pal = getattr(it, 'nr_palety', None) or (it.get('nr_palety') if isinstance(it, dict) else '-')
            batch = getattr(it, 'batch_number', None) or (it.get('batch_number') if isinstance(it, dict) else '-')
            qty = float(getattr(it, 'loaded_qty', 0.0) or getattr(it, 'requested_qty', 0.0) or (it.get('loaded_qty', 0.0) if isinstance(it, dict) else it.get('requested_qty', 0.0)) or 0.0)
            unit = getattr(it, 'unit', 'kg') or (it.get('unit', 'kg') if isinstance(it, dict) else 'kg')
            it_status = getattr(it, 'status', 'RECEIVED') or (it.get('status') if isinstance(it, dict) else 'RECEIVED')
            total_qty += qty

            sum_key = (prod, unit, it_status)
            if sum_key not in summary_products:
                summary_products[sum_key] = {'count': 0, 'total_qty': 0.0}
            summary_products[sum_key]['count'] += 1
            summary_products[sum_key]['total_qty'] += qty

            rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{prod}</td>
                <td style="padding: 10px 12px; font-family: monospace; font-weight: 700; color: #1e293b; background: #f8fafc; text-align: center;">{nr_pal}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{batch}</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #166534;">{qty:,.2f} {unit}</td>
                <td style="padding: 10px 12px; text-align: center;"><span style="display:inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #dcfce7; color: #15803d;">{it_status}</span></td>
            </tr>
            """

        if not rows_html:
            rows_html = '<tr><td colspan="6" style="padding: 16px; text-align: center; color: #64748b;">Brak pozycji w zleceniu.</td></tr>'

        summary_rows_html = ""
        for s_idx, ((pname, unit, it_status), s_data) in enumerate(sorted(summary_products.items(), key=lambda x: (x[0][0].lower(), x[0][2])), start=1):
            summary_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{s_idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{pname}</td>
                <td style="padding: 10px 12px; text-align: center; font-weight: 800; color: #4338ca;">{s_data['count']} szt.</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #166534;">{s_data['total_qty']:,.2f} {unit}</td>
                <td style="padding: 10px 12px; text-align: center;"><span style="display:inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #dcfce7; color: #15803d;">{it_status}</span></td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, #065f46, #059669); padding: 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">Raport Realizacji: Przesunięcie MM</div>
                    <div style="font-size: 22px; font-weight: 900; margin-top: 4px;">🔄 Przesunięcie MM: {source} ➔ {dest}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Przesunięcie MM nr: <strong>{code}</strong> | Status: <strong>ZAKOŃCZONE ({status})</strong></div>
                </div>

                <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <tr>
                            <td style="color: #64748b; padding: 5px 0; width: 40%;">Magazyn wydający (Skąd):</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{source}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Magazyn docelowy (Dokąd):</td>
                            <td style="font-weight: 800; color: #4338ca; text-align: right;">{dest}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Otworzył / Wydał:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{created_by} ({created_str})</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Przyjął / Zatwierdził:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{completed_by} ({completed_str})</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Liczba palet:</td>
                            <td style="font-weight: 800; color: #4338ca; text-align: right;">{total_pallets} szt.</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Łączna ilość towaru:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{total_qty:,.2f} kg</td>
                        </tr>
                        {f'<tr><td style="color: #64748b; padding: 5px 0;">Uwagi:</td><td style="font-weight: 600; color: #334155; text-align: right;">{notes}</td></tr>' if notes and notes != '-' else ''}
                    </table>
                </div>

                <div style="padding: 24px 24px 12px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Wykaz przyjętych palet:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center;">Nr Palety</th>
                                <th style="padding: 10px 12px; text-align: center;">Partia</th>
                                <th style="padding: 10px 12px; text-align: right;">Ilość</th>
                                <th style="padding: 10px 12px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                        <tfoot>
                            <tr style="background: #f8fafc; font-weight: 800; border-top: 2px solid #cbd5e1;">
                                <td colspan="4" style="padding: 12px; text-align: right; color: #0f172a;">SUMA ŁĄCZNA:</td>
                                <td style="padding: 12px; text-align: right; color: #166534; font-size: 14px;">{total_qty:,.2f}</td>
                                <td></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div style="padding: 12px 24px 24px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Podsumowanie zbiorcze według produktów:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center; width: 100px;">Liczba Palet</th>
                                <th style="padding: 10px 12px; text-align: right; width: 130px;">Łączna Ilość</th>
                                <th style="padding: 10px 12px; text-align: center; width: 90px;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {summary_rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; text-align: center;">
                    Wiadomość wygenerowana automatycznie po przyjęciu towaru w systemie RaportProdukcyjny. Do wiadomości dołączono oficjalny dokument PDF w układzie do druku A4.
                </div>
            </div>
        </body>
        </html>
        """

    def build_delivery_report_html(self, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        """Buduje raport HTML z wyraźnym rozróżnieniem Dostawa Centrala / Dostawa OSIP / Przesunięcie MM."""
        cat = self.categorize_delivery_doc(dostawa, items)
        ref = cat['ref']
        notes = dostawa.get('uwagi') or '-'

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        summary_products = {}
        for idx, it in enumerate(items, start=1):
            prod = it.get('productName') or 'Brak nazwy'
            nr_pal = it.get('nr_palety') or '-'
            nr_partii = it.get('nr_partii') or '-'
            raw_qty = it.get('quantity') or it.get('netWeight') or it.get('unitsPerPallet') or 0
            try:
                qty = float(raw_qty)
            except (ValueError, TypeError):
                qty = 0.0
            unit = 'szt' if it.get('packageForm') == 'packaging' else 'kg'
            target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
            accepted = bool(it.get('accepted'))
            status_badge = '<span style="display:inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #dcfce7; color: #15803d;">PRZYJĘTA</span>' if accepted else '<span style="display:inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #fee2e2; color: #b91c1c;">ODRZUCONA</span>'
            status_txt = "PRZYJĘTA" if accepted else "ODRZUCONA"
            total_qty += qty

            sum_key = (prod, unit, status_txt)
            if sum_key not in summary_products:
                summary_products[sum_key] = {'count': 0, 'total_qty': 0.0, 'badge': status_badge}
            summary_products[sum_key]['count'] += 1
            summary_products[sum_key]['total_qty'] += qty

            rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{prod}</td>
                <td style="padding: 10px 12px; font-family: monospace; font-weight: 700; color: #1e293b; background: #f8fafc; text-align: center;">{nr_pal}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{nr_partii}</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #166534;">{qty:,.2f} {unit}</td>
                <td style="padding: 10px 12px; text-align: center; font-weight: 700; color: #2563eb;">{target_spot}</td>
                <td style="padding: 10px 12px; text-align: center;">{status_badge}</td>
            </tr>
            """

        if not rows_html:
            rows_html = '<tr><td colspan="7" style="padding: 16px; text-align: center; color: #64748b;">Brak pozycji w dokumencie.</td></tr>'

        summary_rows_html = ""
        for s_idx, ((pname, unit, status_txt), s_data) in enumerate(sorted(summary_products.items(), key=lambda x: (x[0][0].lower(), x[0][2])), start=1):
            summary_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{s_idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{pname}</td>
                <td style="padding: 10px 12px; text-align: center; font-weight: 800; color: {cat['theme_color_to']};">{s_data['count']} szt.</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #166534;">{s_data['total_qty']:,.2f} {unit}</td>
                <td style="padding: 10px 12px; text-align: center;">{s_data['badge']}</td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 740px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, {cat['theme_color_from']}, {cat['theme_color_to']}); padding: 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">{cat['header_title']}</div>
                    <div style="font-size: 22px; font-weight: 900; margin-top: 4px;">📦 WZ / Nr: {ref}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Trasa: <strong>{cat['source_value']}</strong> ➔ <strong>{cat['dest_value']}</strong></div>
                </div>

                <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <tr>
                            <td style="color: #64748b; padding: 5px 0; width: 38%;">{cat['source_label']}:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{cat['source_value']}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{cat['dest_label']}:</td>
                            <td style="font-weight: 800; color: {cat['theme_color_to']}; text-align: right;">{cat['dest_value']}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{cat['creator_label']}:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{cat['creator_value']}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{cat['acceptor_label']}:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{cat['acceptor_value']}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Liczba palet:</td>
                            <td style="font-weight: 800; color: {cat['theme_color_to']}; text-align: right;">{total_pallets} szt.</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Łączna ilość towaru:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{total_qty:,.2f}</td>
                        </tr>
                        {f'<tr><td style="color: #64748b; padding: 5px 0;">Uwagi:</td><td style="font-weight: 600; color: #334155; text-align: right;">{notes}</td></tr>' if notes and notes != '-' else ''}
                    </table>
                </div>

                <div style="padding: 24px 24px 12px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Wykaz przyjętych palet:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center;">Nr Palety</th>
                                <th style="padding: 10px 12px; text-align: center;">Partia</th>
                                <th style="padding: 10px 12px; text-align: right;">Ilość</th>
                                <th style="padding: 10px 12px; text-align: center;">Lokalizacja</th>
                                <th style="padding: 10px 12px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                        <tfoot>
                            <tr style="background: #f8fafc; font-weight: 800; border-top: 2px solid #cbd5e1;">
                                <td colspan="4" style="padding: 12px; text-align: right; color: #0f172a;">SUMA:</td>
                                <td style="padding: 12px; text-align: right; color: #166534; font-size: 14px;">{total_qty:,.2f}</td>
                                <td colspan="2"></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>

                <div style="padding: 12px 24px 24px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Podsumowanie zbiorcze według produktów:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center; width: 100px;">Liczba Palet</th>
                                <th style="padding: 10px 12px; text-align: right; width: 130px;">Łączna Ilość</th>
                                <th style="padding: 10px 12px; text-align: center; width: 90px;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {summary_rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; text-align: center;">
                    Wiadomość wygenerowana automatycznie po przyjęciu towaru w systemie RaportProdukcyjny. Do wiadomości dołączono oficjalny dokument PDF w układzie do druku A4.
                </div>
            </div>
        </body>
        </html>
        """

    def generate_delivery_pdf(self, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[str]:
        """Generuje plik PDF gotowy do druku A4 dla przyjęcia dostawy/przesunięcia MM."""
        cat = self.categorize_delivery_doc(dostawa, items)
        ref = cat['ref']
        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        summary_products = {}
        for idx, it in enumerate(items, start=1):
            pname = it.get('product_name') or it.get('productName') or 'Brak nazwy'
            nr_pal = it.get('nr_palety') or '-'
            nr_partii = it.get('nr_partii') or '-'
            prod_date = it.get('data_produkcji') or '-'
            exp_date = it.get('data_przydatnosci') or '-'
            raw_q = it.get('quantity') or it.get('netWeight') or it.get('unitsPerPallet') or 0
            try:
                qty = float(raw_q)
            except Exception:
                qty = 0.0
            unit = it.get('unit') or ('szt' if it.get('packageForm') == 'packaging' else 'kg')
            source_spot = it.get('source_spot') or it.get('sourceSpot') or cat['source_value']
            target_spot = it.get('target_spot') or it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
            accepted = bool(it.get('accepted'))
            status_txt = "PRZYJĘTA" if accepted else "ODRZUCONA"
            status_color = "#166534" if accepted else "#991b1b"
            total_qty += qty

            sum_key = (pname, unit, status_txt)
            if sum_key not in summary_products:
                summary_products[sum_key] = {'count': 0, 'total_qty': 0.0, 'color': status_color}
            summary_products[sum_key]['count'] += 1
            summary_products[sum_key]['total_qty'] += qty

            rows_html += f"""
            <tr>
                <td style="text-align: center;">{idx}</td>
                <td><strong>{pname}</strong></td>
                <td style="text-align: center; font-family: monospace; font-weight: 700;">{nr_pal}</td>
                <td style="text-align: center;">{nr_partii}</td>
                <td style="text-align: center;">{prod_date}</td>
                <td style="text-align: center;">{exp_date}</td>
                <td style="text-align: right; font-weight: 700;">{qty:,.2f} {unit}</td>
                <td style="text-align: center;">{source_spot}</td>
                <td style="text-align: center; font-weight: 700; color: #1e40af;">{target_spot}</td>
                <td style="text-align: center; font-weight: 700; color: {status_color};">{status_txt}</td>
            </tr>
            """

        summary_rows_html = ""
        for s_idx, ((pname, unit, status_txt), s_data) in enumerate(sorted(summary_products.items(), key=lambda x: (x[0][0].lower(), x[0][2])), start=1):
            summary_rows_html += f"""
            <tr>
                <td style="text-align: center;">{s_idx}</td>
                <td><strong>{pname}</strong></td>
                <td style="text-align: center; font-weight: 700; color: #2563eb;">{s_data['count']} szt.</td>
                <td style="text-align: right; font-weight: 800; color: #166534;">{s_data['total_qty']:,.2f} {unit}</td>
                <td style="text-align: center; font-weight: 700; color: {s_data['color']};">{status_txt}</td>
            </tr>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="utf-8">
    <title>{cat['doc_title']} - {ref}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 12mm 10mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            color: #0f172a;
            margin: 0;
            padding: 0;
            font-size: 11px;
            line-height: 1.3;
        }}
        .header-box {{
            border: 2px solid #0f172a;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 12px;
            background: #f8fafc;
        }}
        .doc-title {{
            font-size: 18px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 6px 0;
            color: #0f172a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .doc-meta {{
            font-size: 11px;
            color: #475569;
            margin-bottom: 8px;
        }}
        .grid-4 {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #cbd5e1;
        }}
        .meta-item {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        .meta-label {{
            font-size: 9px;
            text-transform: uppercase;
            color: #64748b;
            font-weight: 700;
            margin-bottom: 2px;
        }}
        .meta-val {{
            font-size: 11px;
            font-weight: 800;
            color: #0f172a;
            word-break: break-word;
        }}
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            margin-bottom: 12px;
            font-size: 10px;
        }}
        table.data-table th, table.data-table td {{
            border: 1px solid #cbd5e1;
            padding: 6px 6px;
        }}
        table.data-table th {{
            background: #e2e8f0;
            color: #1e293b;
            font-weight: 800;
            text-transform: uppercase;
            font-size: 9px;
            letter-spacing: 0.3px;
        }}
        table.data-table tr:nth-child(even) {{
            background: #f8fafc;
        }}
        .summary-box {{
            display: flex;
            justify-content: space-between;
            background: #f1f5f9;
            border: 1.5px solid #94a3b8;
            border-radius: 6px;
            padding: 10px 14px;
            font-weight: 800;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        .signatures {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-top: 30px;
            padding-top: 10px;
        }}
        .sign-box {{
            border-top: 1px dashed #64748b;
            text-align: center;
            padding-top: 6px;
            font-size: 10px;
            font-weight: 700;
            color: #475569;
        }}
        .footer {{
            margin-top: 25px;
            font-size: 8px;
            color: #94a3b8;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 6px;
        }}
    </style>
</head>
<body>
    <div class="header-box">
        <div class="doc-title">
            <span>{cat['doc_title']}</span>
            <span style="color: #2563eb;">WZ: {ref}</span>
        </div>
        <div class="doc-meta">Wygenerowano w systemie produkcyjnym: <strong>{gen_now}</strong> | Status: <strong>ZAKOŃCZONE (COMPLETED)</strong></div>
        <div class="grid-4">
            <div class="meta-item">
                <div class="meta-label">{cat['source_label']}</div>
                <div class="meta-val">{cat['source_value']}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">{cat['dest_label']}</div>
                <div class="meta-val" style="color: #1e40af;">{cat['dest_value']}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">{cat['creator_label']}</div>
                <div class="meta-val">{cat['creator_value']}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">{cat['acceptor_label']}</div>
                <div class="meta-val" style="color: #166534;">{cat['acceptor_value']}</div>
            </div>
        </div>
    </div>

    <table class="data-table">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt</th>
                <th style="text-align: center;">Nr Palety (SSCC)</th>
                <th style="text-align: center;">Partia</th>
                <th style="text-align: center;">Data Prod.</th>
                <th style="text-align: center;">Data Przyd.</th>
                <th style="text-align: right;">Ilość</th>
                <th style="text-align: center;">Skąd</th>
                <th style="text-align: center;">Dokąd</th>
                <th style="text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div style="font-size: 11px; font-weight: 800; color: #0f172a; margin-top: 14px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
        PODSUMOWANIE ZBIORCZE WEDŁUG PRODUKTÓW:
    </div>
    <table class="data-table">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Nazwa Produktu</th>
                <th style="text-align: center; width: 100px;">Liczba Palet</th>
                <th style="text-align: right; width: 130px;">Łączna Ilość</th>
                <th style="text-align: center; width: 90px;">Status</th>
            </tr>
        </thead>
        <tbody>
            {summary_rows_html}
        </tbody>
        <tfoot>
            <tr style="background: #f1f5f9; font-weight: 800;">
                <td colspan="2" style="text-align: right;">ŁĄCZNIE:</td>
                <td style="text-align: center; color: #2563eb;">{total_pallets} szt.</td>
                <td style="text-align: right; color: #166534;">{total_qty:,.2f}</td>
                <td></td>
            </tr>
        </tfoot>
    </table>

    <div class="summary-box">
        <div>ŁĄCZNIE PRZYJĘTO PALET: <span style="color: #2563eb;">{total_pallets} szt.</span></div>
        <div>SUMA ILOŚCI TOWARU: <span style="color: #166534;">{total_qty:,.2f}</span></div>
    </div>

    <div class="signatures">
        <div class="sign-box">
            Podpis wydającego / kierowcy ({cat['created_by']})
        </div>
        <div class="sign-box">
            Podpis magazyniera przyjmującego ({cat['accepted_by']})
        </div>
    </div>

    <div class="footer">
        RaportProdukcyjny — Automatyczny wydruk z systemu magazynowego. Dokument stanowi oficjalne potwierdzenie przyjęcia towaru.
    </div>
</body>
</html>
"""
        return self._render_html_to_temp_pdf(html_content, prefix=f"raport_{cat['doc_type_code']}_{ref}_")

    def generate_transfer_pdf(self, transfer: Any) -> Optional[str]:
        """Generuje plik PDF do druku A4 dla zlecenia transferu OSIP."""
        code = getattr(transfer, 'transfer_code', '') or f"TR-{getattr(transfer, 'id', '')}"
        source = getattr(transfer, 'source_warehouse', '') or 'Centrala'
        dest = getattr(transfer, 'destination_warehouse', '') or 'OSIP'
        created_by = getattr(transfer, 'created_by', '') or getattr(transfer, 'dispatched_by', '') or 'System'
        completed_by = getattr(transfer, 'completed_by', None) or getattr(transfer, 'updated_by', None) or '-'
        
        created_at = getattr(transfer, 'created_at', None)
        completed_at = getattr(transfer, 'completed_at', None) or getattr(transfer, 'updated_at', None) or created_at
        
        created_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at and hasattr(created_at, 'strftime') else (str(created_at) if created_at else '-')
        completed_str = completed_at.strftime('%Y-%m-%d %H:%M') if completed_at and hasattr(completed_at, 'strftime') else (str(completed_at) if completed_at else '-')
        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        raw_items = getattr(transfer, 'items', []) or []
        items = raw_items if isinstance(raw_items, list) else []

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        summary_products = {}
        for idx, it in enumerate(items, start=1):
            pname = getattr(it, 'product_name', None) or (it.get('product_name') if isinstance(it, dict) else '') or 'Brak nazwy'
            nr_pal = getattr(it, 'nr_palety', None) or (it.get('nr_palety') if isinstance(it, dict) else '') or '-'
            batch = getattr(it, 'batch_number', None) or (it.get('batch_number') if isinstance(it, dict) else '') or '-'
            prod_date = getattr(it, 'production_date', None) or (it.get('production_date') if isinstance(it, dict) else '') or '-'
            exp_date = getattr(it, 'expiry_date', None) or (it.get('expiry_date') if isinstance(it, dict) else '') or '-'
            raw_q = getattr(it, 'loaded_qty', None) or getattr(it, 'requested_qty', None) or (it.get('loaded_qty') or it.get('requested_qty') if isinstance(it, dict) else 0)
            try:
                qty = float(raw_q or 0)
            except Exception:
                qty = 0.0
            unit = getattr(it, 'unit', None) or (it.get('unit') if isinstance(it, dict) else 'kg') or 'kg'
            loc = getattr(it, 'target_location', None) or (it.get('target_location') if isinstance(it, dict) else '') or dest
            status_txt = getattr(it, 'status', None) or (it.get('status') if isinstance(it, dict) else 'RECEIVED')
            total_qty += qty

            sum_key = (pname, unit, status_txt)
            if sum_key not in summary_products:
                summary_products[sum_key] = {'count': 0, 'total_qty': 0.0}
            summary_products[sum_key]['count'] += 1
            summary_products[sum_key]['total_qty'] += qty

            rows_html += f"""
            <tr>
                <td style="text-align: center;">{idx}</td>
                <td><strong>{pname}</strong></td>
                <td style="text-align: center; font-family: monospace; font-weight: 700;">{nr_pal}</td>
                <td style="text-align: center;">{batch}</td>
                <td style="text-align: center;">{prod_date}</td>
                <td style="text-align: center;">{exp_date}</td>
                <td style="text-align: right; font-weight: 700;">{qty:,.2f} {unit}</td>
                <td style="text-align: center;">{source}</td>
                <td style="text-align: center; font-weight: 700; color: #1e40af;">{loc}</td>
                <td style="text-align: center; font-weight: 700; color: #166534;">{status_txt}</td>
            </tr>
            """

        summary_rows_html = ""
        for s_idx, ((pname, unit, status_txt), s_data) in enumerate(sorted(summary_products.items(), key=lambda x: (x[0][0].lower(), x[0][2])), start=1):
            summary_rows_html += f"""
            <tr>
                <td style="text-align: center;">{s_idx}</td>
                <td><strong>{pname}</strong></td>
                <td style="text-align: center; font-weight: 700; color: #2563eb;">{s_data['count']} szt.</td>
                <td style="text-align: right; font-weight: 800; color: #166534;">{s_data['total_qty']:,.2f} {unit}</td>
                <td style="text-align: center; font-weight: 700; color: #166534;">{status_txt}</td>
            </tr>
            """

        doc_title = f"Przesunięcie MM: {source} ➔ {dest}"
        html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="utf-8">
    <title>{doc_title} - {code}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 12mm 10mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            color: #0f172a;
            margin: 0;
            padding: 0;
            font-size: 11px;
            line-height: 1.3;
        }}
        .header-box {{
            border: 2px solid #0f172a;
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 12px;
            background: #f8fafc;
        }}
        .doc-title {{
            font-size: 18px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 6px 0;
            color: #0f172a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .doc-meta {{
            font-size: 11px;
            color: #475569;
            margin-bottom: 8px;
        }}
        .grid-4 {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #cbd5e1;
        }}
        .meta-item {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        .meta-label {{
            font-size: 9px;
            text-transform: uppercase;
            color: #64748b;
            font-weight: 700;
            margin-bottom: 2px;
        }}
        .meta-val {{
            font-size: 11px;
            font-weight: 800;
            color: #0f172a;
            word-break: break-word;
        }}
        table.data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            margin-bottom: 12px;
            font-size: 10px;
        }}
        table.data-table th, table.data-table td {{
            border: 1px solid #cbd5e1;
            padding: 6px 6px;
        }}
        table.data-table th {{
            background: #e2e8f0;
            color: #1e293b;
            font-weight: 800;
            text-transform: uppercase;
            font-size: 9px;
            letter-spacing: 0.3px;
        }}
        table.data-table tr:nth-child(even) {{
            background: #f8fafc;
        }}
        .summary-box {{
            display: flex;
            justify-content: space-between;
            background: #f1f5f9;
            border: 1.5px solid #94a3b8;
            border-radius: 6px;
            padding: 10px 14px;
            font-weight: 800;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        .signatures {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-top: 30px;
            padding-top: 10px;
        }}
        .sign-box {{
            border-top: 1px dashed #64748b;
            text-align: center;
            padding-top: 6px;
            font-size: 10px;
            font-weight: 700;
            color: #475569;
        }}
        .footer {{
            margin-top: 25px;
            font-size: 8px;
            color: #94a3b8;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 6px;
        }}
    </style>
</head>
<body>
    <div class="header-box">
        <div class="doc-title">
            <span>{doc_title}</span>
            <span style="color: #2563eb;">Nr: {code}</span>
        </div>
        <div class="doc-meta">Wygenerowano w systemie produkcyjnym: <strong>{gen_now}</strong> | Status: <strong>ZAKOŃCZONE (COMPLETED)</strong></div>
        <div class="grid-4">
            <div class="meta-item">
                <div class="meta-label">MAGAZYN WYDAJĄCY (SKĄD)</div>
                <div class="meta-val">{source}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">MAGAZYN DOCELOWY (DOKĄD)</div>
                <div class="meta-val" style="color: #1e40af;">{dest}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">WYDAŁ / OTWORZYŁ</div>
                <div class="meta-val">{created_by} ({created_str})</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">PRZYJĄŁ / ZATWIERDZIŁ</div>
                <div class="meta-val" style="color: #166534;">{completed_by} ({completed_str})</div>
            </div>
        </div>
    </div>

    <table class="data-table">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt</th>
                <th style="text-align: center;">Nr Palety (SSCC)</th>
                <th style="text-align: center;">Partia</th>
                <th style="text-align: center;">Data Prod.</th>
                <th style="text-align: center;">Data Przyd.</th>
                <th style="text-align: right;">Ilość</th>
                <th style="text-align: center;">Skąd</th>
                <th style="text-align: center;">Dokąd</th>
                <th style="text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div style="font-size: 11px; font-weight: 800; color: #0f172a; margin-top: 14px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
        PODSUMOWANIE ZBIORCZE WEDŁUG PRODUKTÓW:
    </div>
    <table class="data-table">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Nazwa Produktu</th>
                <th style="text-align: center; width: 100px;">Liczba Palet</th>
                <th style="text-align: right; width: 130px;">Łączna Ilość</th>
                <th style="text-align: center; width: 90px;">Status</th>
            </tr>
        </thead>
        <tbody>
            {summary_rows_html}
        </tbody>
        <tfoot>
            <tr style="background: #f1f5f9; font-weight: 800;">
                <td colspan="2" style="text-align: right;">ŁĄCZNIE:</td>
                <td style="text-align: center; color: #2563eb;">{total_pallets} szt.</td>
                <td style="text-align: right; color: #166534;">{total_qty:,.2f}</td>
                <td></td>
            </tr>
        </tfoot>
    </table>

    <div class="signatures">
        <div class="sign-box">
            Podpis wydającego / kierowcy ({created_by})
        </div>
        <div class="sign-box">
            Podpis magazyniera przyjmującego ({completed_by})
        </div>
    </div>

    <div class="footer">
        RaportProdukcyjny — Automatyczny wydruk z systemu magazynowego. Dokument stanowi oficjalne potwierdzenie przyjęcia transferu.
    </div>
</body>
</html>
"""
        return self._render_html_to_temp_pdf(html_content, prefix=f"raport_transferu_{code}_")

    def send_osip_transfer_report(self, transfer_id: Any) -> Tuple[bool, str]:
        """
        Wysyła raport e-mail po przyjęciu zlecenia transferu (w tym transferów OSIP) wraz z załącznikiem PDF.
        Gwarantuje jednorazową wysyłkę (idempotentność) poprzez blokadę wątkową oraz pole email_sent_at w bazie.
        """
        dispatch_key = f"transfer_{transfer_id}"
        with self._dispatch_lock:
            if dispatch_key in self._active_dispatches:
                return False, f"Wysyłka e-mail dla transferu {transfer_id} jest już w toku."
            self._active_dispatches.add(dispatch_key)

        try:
            from app.repositories.osip_transfer_repository import OsipTransferRepository
            repo = OsipTransferRepository()
            transfer = repo.get_transfer_by_id(transfer_id)
            if not transfer:
                return False, f"Nie znaleziono transferu o ID/kodzie: {transfer_id}"

            # Zabezpieczenie przed ponowną wysyłką
            if getattr(transfer, 'email_sent_at', None):
                sent_at = transfer.email_sent_at
                sent_str = sent_at.strftime('%Y-%m-%d %H:%M') if hasattr(sent_at, 'strftime') else str(sent_at)
                return False, f"Raport e-mail dla transferu {transfer.transfer_code} został już wcześniej wysłany ({sent_str})."

            config = self.settings_repo.get_settings()
            if not config.is_active:
                return False, "Moduł wysyłki e-mail jest wyłączony w ustawieniach."

            if not config.is_configured:
                return False, "Dedykowane konto e-mail nadawcy nie zostało jeszcze skonfigurowane."

            recipients = config.recipients_list
            if not recipients:
                return False, "Brak zdefiniowanych adresów e-mail odbiorców w Ustawieniach E-mail."

            source = getattr(transfer, 'source_warehouse', '') or 'Centrala'
            dest = getattr(transfer, 'destination_warehouse', '') or 'OSIP'
            code = getattr(transfer, 'transfer_code', '') or f"TR-{transfer_id}"
            
            subject = f"Przesunięcie MM nr: {code} ({source} ➔ {dest})"
            body_html = self.build_transfer_report_html(transfer)

            pdf_path = None
            try:
                pdf_path = self.generate_transfer_pdf(transfer)
                attachments = [pdf_path] if (pdf_path and os.path.exists(pdf_path)) else None
                ok, msg = self._send_raw_email(config, recipients, subject, body_html, attachments=attachments)
                if ok:
                    conn = get_db_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE osip_transfers SET email_sent_at = NOW(), email_sent_to = %s WHERE id = %s AND email_sent_at IS NULL",
                            (", ".join(recipients)[:500], transfer.id)
                        )
                        conn.commit()
                        cursor.close()
                    finally:
                        conn.close()
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

    def send_central_delivery_osip_report(self, dostawa_id: Any) -> Tuple[bool, str]:
        """
        Wysyła raport e-mail po przyjęciu dostawy lub przesunięcia MM wraz z załącznikiem PDF.
        Gwarantuje jednorazową wysyłkę (idempotentność) poprzez blokadę wątkową oraz pole email_sent_at w bazie.
        """
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

            # Zabezpieczenie przed ponowną wysyłką
            if dostawa.get('email_sent_at'):
                sent_at = dostawa.get('email_sent_at')
                sent_str = sent_at.strftime('%Y-%m-%d %H:%M') if hasattr(sent_at, 'strftime') else str(sent_at)
                return False, f"Raport e-mail dla dokumentu #{dostawa_id} został już wcześniej wysłany ({sent_str})."

            try:
                items = json.loads(dostawa.get('items') or '[]')
            except Exception:
                items = []

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
            body_html = self.build_delivery_report_html(dostawa, items)

            pdf_path = None
            try:
                pdf_path = self.generate_delivery_pdf(dostawa, items)
                attachments = [pdf_path] if (pdf_path and os.path.exists(pdf_path)) else None
                ok, msg = self._send_raw_email(config, recipients, subject, body_html, attachments=attachments)
                if ok:
                    conn = get_db_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE magazyn_dostawy SET email_sent_at = NOW(), email_sent_to = %s WHERE id = %s AND email_sent_at IS NULL",
                            (", ".join(recipients)[:500], dostawa_id)
                        )
                        conn.commit()
                        cursor.close()
                    finally:
                        conn.close()
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

    def get_daily_warehouse_activity(self, date_str: str, central_only: bool = True) -> Dict[str, Any]:
        """
        Pobiera wszystkie zrealizowane w danym dniu dostawy zewnętrzne oraz przesunięcia MM / transfery.
        Domyślnie (central_only=True) filtruje i uwzględnia wyłącznie operacje Magazynu Centralnego,
        wykluczając dostawy na OSIP oraz wywozy/transfery z i do OSIP.
        Zwraca ustrukturyzowane dane z wyraźnym podziałem na Dostawy oraz Przesunięcia.
        """
        conn = get_db_connection()
        dostawy_rows = []
        osip_transfers_rows = []
        osip_items_by_transfer = {}
        try:
            cursor = conn.cursor(dictionary=True)
            # 1. Pobierz dokumenty z magazyn_dostawy
            cursor.execute("""
                SELECT * FROM magazyn_dostawy 
                WHERE status = 'COMPLETED' 
                  AND (
                      DATE(potwierdzone_at) = %s 
                      OR (potwierdzone_at IS NULL AND DATE(created_at) = %s)
                      OR (potwierdzone_at IS NULL AND delivery_date = %s)
                  )
                ORDER BY created_at ASC
            """, (date_str, date_str, date_str))
            dostawy_rows = cursor.fetchall() or []

            # 2. Pobierz transfery z osip_transfers (tylko jeśli nie wymuszono wyłącznie Centrali)
            if not central_only:
                try:
                    cursor.execute("""
                        SELECT * FROM osip_transfers 
                        WHERE status = 'COMPLETED'
                          AND (
                              DATE(completed_at) = %s 
                              OR (completed_at IS NULL AND DATE(created_at) = %s)
                          )
                        ORDER BY created_at ASC
                    """, (date_str, date_str))
                    osip_transfers_rows = cursor.fetchall() or []

                    if osip_transfers_rows:
                        t_ids = [t['id'] for t in osip_transfers_rows]
                        placeholders = ','.join(['%s'] * len(t_ids))
                        cursor.execute(f"""
                            SELECT * FROM osip_transfer_items 
                            WHERE transfer_id IN ({placeholders})
                            ORDER BY id ASC
                        """, tuple(t_ids))
                        all_it_rows = cursor.fetchall() or []
                        for it in all_it_rows:
                            tid = it['transfer_id']
                            if tid not in osip_items_by_transfer:
                                osip_items_by_transfer[tid] = []
                            osip_items_by_transfer[tid].append(it)
                except Exception:
                    osip_transfers_rows = []
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            conn.close()

        deliveries = []
        transfers = []
        deliveries_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        transfers_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        all_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        total_pallets = 0
        total_qty_by_unit: Dict[str, float] = {}

        # Przetwarzanie magazyn_dostawy
        for d in dostawy_rows:
            try:
                raw_items = json.loads(d.get('items') or '[]')
            except Exception:
                raw_items = []
            
            cat = self.categorize_delivery_doc(d, raw_items)

            # Filtrowanie OSIP dla raportu dziennego Magazynu Centralnego
            if central_only:
                is_osip = (
                    cat.get('is_osip')
                    or cat.get('doc_type_code') == 'DOSTAWA_OSIP'
                    or self.is_osip_involved(d.get('lokalizacja_z') or cat.get('source_value'), d.get('lokalizacja_do') or cat.get('dest_value'), raw_items)
                )
                if is_osip:
                    continue

                # Dla przesunięć MM: weryfikacja czy nagłówek dokumentu nie wskazuje nieautoryzowanej strefy
                if not cat['is_external']:
                    doc_src = d.get('lokalizacja_z') or cat.get('source_value')
                    doc_dst = d.get('lokalizacja_do') or cat.get('dest_value')
                    neutral_keywords = {'WIELE', 'MAGAZYN', 'CENTRALA', 'MAGAZYNCENTRALNY', 'CENTRALNY', ''}
                    src_norm = re.sub(r'[^A-Z0-9]', '', str(doc_src or '').upper())
                    dst_norm = re.sub(r'[^A-Z0-9]', '', str(doc_dst or '').upper())
                    if doc_src and not self.is_allowed_central_warehouse_location(doc_src) and src_norm not in neutral_keywords:
                        continue
                    if doc_dst and not self.is_allowed_central_warehouse_location(doc_dst) and dst_norm not in neutral_keywords:
                        continue

            doc_items = []
            doc_summary_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for it in raw_items:
                source_spot = it.get('sourceSpot') or it.get('lokalizacja_z') or cat['source_value']
                target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or it.get('lokalizacja_do') or cat['dest_value']

                # Dla raportu Magazynu Centralnego: przesunięcia MM mogą dotyczyć wyłącznie dozwolonych regałów i buforów
                if central_only and not cat['is_external']:
                    if not self.is_allowed_central_transfer(source_spot, target_spot):
                        continue

                pname_raw = it.get('productName') or 'Brak nazwy'
                pname = re.sub(r'\s+', ' ', str(pname_raw).strip())
                nr_pal = it.get('nr_palety') or '-'
                nr_partii = it.get('nr_partii') or '-'
                prod_date = it.get('data_produkcji') or '-'
                exp_date = it.get('data_przydatnosci') or '-'
                raw_q = it.get('quantity') or it.get('netWeight') or it.get('unitsPerPallet') or 0
                try:
                    qty = float(raw_q)
                except Exception:
                    qty = 0.0
                unit = ('szt' if it.get('packageForm') == 'packaging' else 'kg').strip().lower()
                accepted = bool(it.get('accepted'))
                status_txt = "PRZYJĘTA" if accepted else "ODRZUCONA"

                item_obj = {
                    'lp': len(doc_items) + 1,
                    'product_name': pname,
                    'nr_palety': nr_pal,
                    'nr_partii': nr_partii,
                    'data_produkcji': prod_date,
                    'data_przydatnosci': exp_date,
                    'quantity': qty,
                    'unit': unit,
                    'source_spot': source_spot,
                    'target_spot': target_spot,
                    'status': status_txt,
                    'accepted': accepted
                }
                doc_items.append(item_obj)

                # Statystyki dokumentu
                s_key = (pname.lower(), unit)
                if s_key not in doc_summary_map:
                    doc_summary_map[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                doc_summary_map[s_key]['count'] += 1
                doc_summary_map[s_key]['total_qty'] += qty

                # Statystyki łączne
                if s_key not in all_products_summary:
                    all_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                all_products_summary[s_key]['count'] += 1
                all_products_summary[s_key]['total_qty'] += qty

                # Statystyki podzielone na dostawy i przesuniecia
                target_summary = deliveries_products_summary if cat['is_external'] else transfers_products_summary
                if s_key not in target_summary:
                    target_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                target_summary[s_key]['count'] += 1
                target_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            if not doc_items:
                continue

            doc_entry = {
                'id': d.get('id'),
                'order_ref': cat['ref'],
                'doc_type': 'DOSTAWA' if cat['is_external'] else 'PRZESUNIECIE_MM',
                'doc_title': cat['doc_title'],
                'source': cat['source_value'],
                'destination': cat['dest_value'],
                'created_by': cat['created_by'],
                'created_str': cat['created_str'],
                'accepted_by': cat['accepted_by'],
                'accepted_str': cat['accepted_str'],
                'uwagi': d.get('uwagi') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values())
            }

            if cat['is_external']:
                deliveries.append(doc_entry)
            else:
                transfers.append(doc_entry)

        # Przetwarzanie osip_transfers (jeśli nie wykluczone)
        for tr in osip_transfers_rows:
            tr_id = tr.get('id')
            raw_t_items = osip_items_by_transfer.get(tr_id, [])
            code = tr.get('transfer_code') or f"TR-{tr_id}"
            source = tr.get('source_warehouse') or 'Centrala'
            dest = tr.get('destination_warehouse') or 'OSIP'

            if central_only and self.is_osip_involved(source, dest, raw_t_items):
                continue
            created_by = tr.get('created_by') or 'System'
            completed_by = tr.get('completed_by') or tr.get('updated_by') or '-'
            created_at = tr.get('created_at')
            completed_at = tr.get('completed_at') or created_at
            created_str = created_at.strftime('%Y-%m-%d %H:%M') if hasattr(created_at, 'strftime') else str(created_at or '-')
            completed_str = completed_at.strftime('%Y-%m-%d %H:%M') if hasattr(completed_at, 'strftime') else str(completed_at or '-')

            doc_items = []
            doc_summary_map = {}

            for idx, it in enumerate(raw_t_items, start=1):
                pname_raw = it.get('product_name') or 'Brak nazwy'
                pname = re.sub(r'\s+', ' ', str(pname_raw).strip())
                nr_pal = it.get('nr_palety') or '-'
                batch = it.get('batch_number') or '-'
                raw_q = it.get('loaded_qty') or it.get('requested_qty') or 0.0
                try:
                    qty = float(raw_q)
                except Exception:
                    qty = 0.0
                unit = str(it.get('unit') or 'kg').strip().lower()
                target_spot = it.get('target_location') or dest
                it_status = it.get('status') or 'RECEIVED'

                item_obj = {
                    'lp': idx,
                    'product_name': pname,
                    'nr_palety': nr_pal,
                    'nr_partii': batch,
                    'data_produkcji': '-',
                    'data_przydatnosci': '-',
                    'quantity': qty,
                    'unit': unit,
                    'source_spot': source,
                    'target_spot': target_spot,
                    'status': it_status,
                    'accepted': it_status == 'RECEIVED'
                }
                doc_items.append(item_obj)

                s_key = (pname.lower(), unit)
                if s_key not in doc_summary_map:
                    doc_summary_map[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                doc_summary_map[s_key]['count'] += 1
                doc_summary_map[s_key]['total_qty'] += qty

                if s_key not in all_products_summary:
                    all_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                all_products_summary[s_key]['count'] += 1
                all_products_summary[s_key]['total_qty'] += qty

                if s_key not in transfers_products_summary:
                    transfers_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                transfers_products_summary[s_key]['count'] += 1
                transfers_products_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            transfers.append({
                'id': tr_id,
                'order_ref': code,
                'doc_type': 'TRANSFER_OSIP',
                'doc_title': f'Transfer Wewnętrzny {source} ➔ {dest}',
                'source': source,
                'destination': dest,
                'created_by': created_by,
                'created_str': created_str,
                'accepted_by': completed_by,
                'accepted_str': completed_str,
                'uwagi': tr.get('notes') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values())
            })

        has_activity = bool(deliveries or transfers)

        return {
            'date_str': date_str,
            'deliveries': deliveries,
            'transfers': transfers,
            'deliveries_count': len(deliveries),
            'transfers_count': len(transfers),
            'total_pallets': total_pallets,
            'total_qty_by_unit': total_qty_by_unit,
            'deliveries_products_summary': sorted(deliveries_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'transfers_products_summary': sorted(transfers_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'all_products_summary': sorted(all_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'has_activity': has_activity
        }

    def build_daily_summary_report_html(self, date_str: str, activity_data: Dict[str, Any]) -> str:
        """Buduje nowoczesny, czytelny raport HTML z podsumowaniem dnia (Rejestr zbiorczy + poszczególne dokumenty osobno)."""
        deliveries = activity_data.get('deliveries', [])
        transfers = activity_data.get('transfers', [])
        total_pallets = activity_data.get('total_pallets', 0)
        total_qty_by_unit = activity_data.get('total_qty_by_unit', {})
        all_products = activity_data.get('all_products_summary', [])
        deliveries_products = activity_data.get('deliveries_products_summary', [])
        transfers_products = activity_data.get('transfers_products_summary', [])
        
        totals_str_parts = [f"<strong>{qty:,.2f} {unit}</strong>" for unit, qty in sorted(total_qty_by_unit.items())]
        totals_display = " | ".join(totals_str_parts) if totals_str_parts else "0 kg"

        # 1. ZBIORCZY REJESTR WSZYSTKICH OPERACJI RAZEM
        all_master_items = []
        for d in deliveries:
            for it in d.get('items', []):
                all_master_items.append({
                    'type_label': 'PZ (Dostawa)',
                    'type_badge_bg': '#dbeafe',
                    'type_badge_color': '#1e40af',
                    'doc_ref': d.get('order_ref'),
                    'source': it.get('source_spot') or d.get('source'),
                    'target': it.get('target_spot') or d.get('destination'),
                    'created_by': d.get('created_by') or '-',
                    'accepted_by': d.get('accepted_by') or '-',
                    'product_name': it.get('product_name'),
                    'nr_palety': it.get('nr_palety'),
                    'nr_partii': it.get('nr_partii'),
                    'quantity': it.get('quantity'),
                    'unit': it.get('unit'),
                    'status': it.get('status'),
                    'accepted': it.get('accepted'),
                })
        for t in transfers:
            for it in t.get('items', []):
                all_master_items.append({
                    'type_label': 'MM (Przesunięcie)',
                    'type_badge_bg': '#dcfce7',
                    'type_badge_color': '#166534',
                    'doc_ref': t.get('order_ref'),
                    'source': it.get('source_spot') or t.get('source'),
                    'target': it.get('target_spot') or t.get('destination'),
                    'created_by': t.get('created_by') or '-',
                    'accepted_by': t.get('accepted_by') or '-',
                    'product_name': it.get('product_name'),
                    'nr_palety': it.get('nr_palety'),
                    'nr_partii': it.get('nr_partii'),
                    'quantity': it.get('quantity'),
                    'unit': it.get('unit'),
                    'status': it.get('status'),
                    'accepted': it.get('accepted'),
                })

        master_rows_html = ""
        for m_idx, m in enumerate(all_master_items, start=1):
            st_badge = '<span style="display:inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; background: #dcfce7; color: #15803d;">PRZYJĘTA</span>' if m.get('accepted') else '<span style="display:inline-block; padding: 2px 7px; border-radius: 999px; font-size: 10px; font-weight: 700; background: #fee2e2; color: #b91c1c;">ODRZUCONA</span>'
            master_rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                <td style="padding: 7px 8px; text-align: center; color: #64748b; font-weight: 600;">{m_idx}</td>
                <td style="padding: 7px 8px; text-align: center;"><span style="display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 800; background: {m['type_badge_bg']}; color: {m['type_badge_color']};">{m['type_label']}</span></td>
                <td style="padding: 7px 8px; text-align: center; font-weight: 800; color: #0f172a;">{m.get('doc_ref')}</td>
                <td style="padding: 7px 8px; font-weight: 700; color: #0f172a;">{m.get('product_name')}</td>
                <td style="padding: 7px 8px; font-family: monospace; font-weight: 700; color: #1e293b; background: #f8fafc; text-align: center;">{m.get('nr_palety')}</td>
                <td style="padding: 7px 8px; text-align: center; color: #475569;">{m.get('nr_partii')}</td>
                <td style="padding: 7px 8px; text-align: right; font-weight: 800; color: #166534;">{m.get('quantity'):,.2f} {m.get('unit')}</td>
                <td style="padding: 7px 8px; text-align: center; color: #475569;">{m.get('source')}</td>
                <td style="padding: 7px 8px; text-align: center; font-weight: 700; color: #2563eb;">{m.get('target')}</td>
                <td style="padding: 7px 8px; text-align: center; font-size: 11px; color: #334155;">{m.get('created_by')}</td>
                <td style="padding: 7px 8px; text-align: center; font-size: 11px; font-weight: 700; color: #166534;">{m.get('accepted_by')}</td>
                <td style="padding: 7px 8px; text-align: center;">{st_badge}</td>
            </tr>
            """

        def _render_doc_block(doc: Dict[str, Any], is_delivery: bool) -> str:
            badge_color = "#1e3a8a" if is_delivery else "#065f46"
            theme_grad = "linear-gradient(135deg, #1e3a8a, #2563eb)" if is_delivery else "linear-gradient(135deg, #065f46, #059669)"
            doc_type_icon = "📦" if is_delivery else "🔄"
            src_label = "Dostawca" if is_delivery else "Skąd"
            dst_label = "Lokalizacja docelowa" if is_delivery else "Dokąd"

            rows_html = ""
            for item in doc.get('items', []):
                status_badge = '<span style="display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #dcfce7; color: #15803d;">PRZYJĘTA</span>' if item.get('accepted') else '<span style="display:inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #fee2e2; color: #b91c1c;">ODRZUCONA</span>'
                rows_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                    <td style="padding: 8px 10px; text-align: center; color: #64748b; font-weight: 600;">{item.get('lp')}</td>
                    <td style="padding: 8px 10px; font-weight: 700; color: #0f172a;">{item.get('product_name')}</td>
                    <td style="padding: 8px 10px; font-family: monospace; font-weight: 700; color: #1e293b; background: #f8fafc; text-align: center;">{item.get('nr_palety')}</td>
                    <td style="padding: 8px 10px; text-align: center; color: #475569;">{item.get('nr_partii')}</td>
                    <td style="padding: 8px 10px; text-align: right; font-weight: 800; color: #166534;">{item.get('quantity'):,.2f} {item.get('unit')}</td>
                    <td style="padding: 8px 10px; text-align: center; font-weight: 700; color: #2563eb;">{item.get('target_spot')}</td>
                    <td style="padding: 8px 10px; text-align: center;">{status_badge}</td>
                </tr>
                """

            summary_rows_html = ""
            for s in doc.get('summary', []):
                summary_rows_html += f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                    <td style="padding: 6px 10px; font-weight: 700; color: #1e293b;">{s.get('product_name')}</td>
                    <td style="padding: 6px 10px; text-align: center; font-weight: 800; color: {badge_color};">{s.get('count')} szt.</td>
                    <td style="padding: 6px 10px; text-align: right; font-weight: 800; color: #166534;">{s.get('total_qty'):,.2f} {s.get('unit')}</td>
                </tr>
                """

            return f"""
            <div style="margin-bottom: 24px; border: 1px solid #cbd5e1; border-radius: 12px; overflow: hidden; background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <div style="background: {theme_grad}; padding: 14px 18px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.9;">{doc_type_icon} {doc.get('doc_title')}</div>
                    <div style="font-size: 18px; font-weight: 900; margin-top: 2px;">Dokument: {doc.get('order_ref')}</div>
                </div>
                <div style="padding: 12px 18px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; font-size: 12px; line-height: 1.6;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="width: 50%; vertical-align: top;">
                                <div><span style="color: #64748b;">{src_label}:</span> <strong>{doc.get('source')}</strong></div>
                                <div><span style="color: #64748b;">{dst_label}:</span> <strong style="color: {badge_color};">{doc.get('destination')}</strong></div>
                            </td>
                            <td style="width: 50%; vertical-align: top;">
                                <div><span style="color: #64748b;">Wprowadził:</span> <strong>{doc.get('created_by')}</strong> ({doc.get('created_str')})</div>
                                <div><span style="color: #64748b;">Przyjął:</span> <strong style="color: #166534;">{doc.get('accepted_by')}</strong> ({doc.get('accepted_str')})</div>
                            </td>
                        </tr>
                    </table>
                </div>
                <div style="padding: 14px 18px;">
                    <div style="font-size: 12px; font-weight: 800; color: #0f172a; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Wykaz pozycji / palet ({doc.get('items_count')} szt.):</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; margin-bottom: 14px;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase;">
                                <th style="padding: 8px 10px; text-align: center; width: 30px;">Lp</th>
                                <th style="padding: 8px 10px; text-align: left;">Produkt</th>
                                <th style="padding: 8px 10px; text-align: center;">Nr Palety</th>
                                <th style="padding: 8px 10px; text-align: center;">Partia</th>
                                <th style="padding: 8px 10px; text-align: right;">Ilość</th>
                                <th style="padding: 8px 10px; text-align: center;">Lokalizacja</th>
                                <th style="padding: 8px 10px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>

                    <div style="font-size: 11px; font-weight: 800; color: #475569; margin-bottom: 6px; text-transform: uppercase;">Podsumowanie pozycji dokumentu:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f8fafc; color: #64748b; font-size: 10px; text-transform: uppercase;">
                                <th style="padding: 6px 10px; text-align: left;">Produkt</th>
                                <th style="padding: 6px 10px; text-align: center; width: 100px;">Liczba Palet</th>
                                <th style="padding: 6px 10px; text-align: right; width: 140px;">Łączna Ilość</th>
                            </tr>
                        </thead>
                        <tbody>
                            {summary_rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        deliveries_blocks = "".join(_render_doc_block(d, is_delivery=True) for d in deliveries) if deliveries else '<div style="padding: 16px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; font-size: 13px; margin-bottom: 20px;">Brak dostaw zewnętrznych w tym dniu.</div>'
        transfers_blocks = "".join(_render_doc_block(t, is_delivery=False) for t in transfers) if transfers else '<div style="padding: 16px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; font-size: 13px; margin-bottom: 20px;">Brak przesunięć MM / transferów w tym dniu.</div>'

        def _render_html_products_rows(prod_list: List[Dict[str, Any]], count_color: str) -> str:
            if not prod_list:
                return '<tr><td colspan="4" style="padding: 12px; text-align: center; color: #64748b;">Brak pozycji w tym zestawieniu.</td></tr>'
            rows = ""
            for idx, p in enumerate(prod_list, start=1):
                rows += f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                    <td style="padding: 8px 12px; text-align: center; color: #64748b; font-weight: 600; width: 35px;">{idx}</td>
                    <td style="padding: 8px 12px; font-weight: 700; color: #0f172a;">{p.get('product_name')}</td>
                    <td style="padding: 8px 12px; text-align: center; font-weight: 800; color: {count_color}; width: 120px;">{p.get('count')} szt.</td>
                    <td style="padding: 8px 12px; text-align: right; font-weight: 800; color: #166534; width: 150px;">{p.get('total_qty'):,.2f} {p.get('unit')}</td>
                </tr>
                """
            return rows

        deliveries_products_rows = _render_html_products_rows(deliveries_products, "#1e3a8a")
        transfers_products_rows = _render_html_products_rows(transfers_products, "#065f46")
        app_base_url = os.getenv('APP_BASE_URL', 'https://raportprodukcji.mycloudnas.com').rstrip('/')
        print_url = f"{app_base_url}/magazyn-dostawy/drukuj-raport-dzienny?data={date_str}"

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 860px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #cbd5e1;">
                
                <!-- Hero Header -->
                <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 28px 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 800; color: #38bdf8;">Magazyn Centralny • Dzienny Raport Zbiorczy</div>
                    <div style="font-size: 24px; font-weight: 900; margin-top: 6px;">📋 Raport Zbiorczy Dostaw i Przesunięć</div>
                    <div style="font-size: 14px; opacity: 0.9; margin-top: 6px;">Dzień: <strong>{date_str}</strong> | Zakres: <strong>Magazyn Centralny</strong> | Wygenerowano: <strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}</strong></div>
                </div>

                <!-- KPI Banner -->
                <div style="padding: 18px 24px; background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; text-align: center;">
                        <tr>
                            <td style="width: 25%; padding: 10px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Dostawy PZ</div>
                                <div style="font-size: 22px; font-weight: 900; color: #1e3a8a; margin-top: 4px;">{len(deliveries)}</div>
                            </td>
                            <td style="width: 25%; padding: 10px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Przesunięcia MM</div>
                                <div style="font-size: 22px; font-weight: 900; color: #065f46; margin-top: 4px;">{len(transfers)}</div>
                            </td>
                            <td style="width: 25%; padding: 10px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Łącznie Palet</div>
                                <div style="font-size: 22px; font-weight: 900; color: #0284c7; margin-top: 4px;">{total_pallets}</div>
                            </td>
                            <td style="width: 25%; padding: 10px;">
                                <div style="font-size: 11px; font-weight: 700; color: #64748b; text-transform: uppercase;">Łączna Ilość</div>
                                <div style="font-size: 16px; font-weight: 900; color: #166534; margin-top: 6px;">{totals_display}</div>
                            </td>
                        </tr>
                    </table>
                </div>

                <!-- Direct 1-Click Print & Attachment Selection Banner -->
                <div style="margin: 20px 24px 8px 24px; padding: 18px 20px; background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 2px solid #bfdbfe; border-radius: 12px; text-align: center; box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08);">
                    <div style="font-size: 14px; font-weight: 800; color: #1e40af; margin-bottom: 4px;">
                        🖨️ DRUKUJ RAPORT I ZAŁĄCZNIKI (WYBÓR 1 KLIKNIĘCIEM)
                    </div>
                    <div style="font-size: 12px; color: #334155; margin-bottom: 12px;">
                        Kliknij poniższy przycisk, aby otworzyć panel wydruku w systemie, wybrać które załączniki PZ / MM chcesz wydrukować i puścić wydruk naraz.
                    </div>
                    <a href="{print_url}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #ffffff; text-decoration: none; font-weight: 900; font-size: 14px; padding: 12px 28px; border-radius: 10px; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); letter-spacing: 0.3px;">
                        🖨️ OTWÓRZ PANEL DRUKU W SYSTEMIE
                    </a>
                </div>

                <div style="padding: 24px;">

                    <!-- SEKCJA 1: JEDNOLITY ZBIORCZY REJESTR WSZYSTKICH POZYCJI RAZEM -->
                    <div style="margin-bottom: 30px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; border-bottom: 2px solid #0f172a; padding-bottom: 8px;">
                            <h2 style="font-size: 16px; font-weight: 900; color: #0f172a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                📑 1. Zbiorczy Rejestr Wszystkich Operacji (Dostawy PZ i Przesunięcia MM razem) [{len(all_master_items)} palet]
                            </h2>
                        </div>
                        <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; margin-bottom: 12px;">
                            <thead>
                                <tr style="background: #f1f5f9; color: #334155; font-size: 11px; text-transform: uppercase;">
                                    <th style="padding: 8px 6px; text-align: center; width: 25px;">Lp</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 85px;">Typ</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 85px;">Dokument</th>
                                    <th style="padding: 8px 6px; text-align: left;">Produkt / Surowiec</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 105px;">Nr Palety</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 70px;">Partia</th>
                                    <th style="padding: 8px 6px; text-align: right; width: 80px;">Ilość</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 60px;">Skąd</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 65px;">Dokąd</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 70px;">Wydał</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 70px;">Przyjął</th>
                                    <th style="padding: 8px 6px; text-align: center; width: 70px;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {master_rows_html}
                            </tbody>
                        </table>
                    </div>

                    <!-- SEKCJA 2.1: DOSTAWY ZEWNĘTRZNE OSOBNO -->
                    <div style="margin-bottom: 30px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; border-bottom: 2px solid #1e3a8a; padding-bottom: 8px;">
                            <h2 style="font-size: 16px; font-weight: 900; color: #1e3a8a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                📦 2.1. Szczegółowe Karty: Przyjęcia Dostaw (PZ) ({len(deliveries)})
                            </h2>
                        </div>
                        {deliveries_blocks}
                    </div>

                    <!-- SEKCJA 2.2: PRZESUNIĘCIA MM OSOBNO -->
                    <div style="margin-bottom: 30px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; border-bottom: 2px solid #065f46; padding-bottom: 8px;">
                            <h2 style="font-size: 16px; font-weight: 900; color: #065f46; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                🔄 2.2. Szczegółowe Karty: Przesunięcia MM i Transfery Wewnętrzne ({len(transfers)})
                            </h2>
                        </div>
                        {transfers_blocks}
                    </div>

                    <!-- SEKCJA 3: PODSUMOWANIE ASORTYMENTU -->
                    <div style="margin-bottom: 16px;">
                        <div style="margin-bottom: 16px; border-bottom: 2px solid #0f172a; padding-bottom: 8px;">
                            <h2 style="font-size: 16px; font-weight: 900; color: #0f172a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                📊 3. Zbiorcze Podsumowanie Asortymentu z Całego Dnia
                            </h2>
                        </div>

                        <!-- 3.1 Dostawy Zewnętrzne -->
                        <div style="margin-bottom: 20px;">
                            <div style="font-size: 12px; font-weight: 800; color: #1e3a8a; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                                📦 3.1. Podsumowanie Asortymentu — Przyjęcia Dostaw (PZ) ({len(deliveries_products)})
                            </div>
                            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background: #eff6ff; color: #1e3a8a; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <th style="padding: 8px 12px; text-align: center; width: 35px;">Lp</th>
                                        <th style="padding: 8px 12px; text-align: left;">Produkt / Surowiec / Opakowanie</th>
                                        <th style="padding: 8px 12px; text-align: center; width: 120px;">Liczba Palet</th>
                                        <th style="padding: 8px 12px; text-align: right; width: 150px;">Łączna Ilość</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {deliveries_products_rows}
                                </tbody>
                            </table>
                        </div>

                        <!-- 3.2 Przesunięcia MM i Transfery Wewnętrzne -->
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 12px; font-weight: 800; color: #065f46; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                                🔄 3.2. Podsumowanie Asortymentu — Przesunięcia MM i Transfery Wewnętrzne ({len(transfers_products)})
                            </div>
                            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background: #f0fdf4; color: #065f46; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <th style="padding: 8px 12px; text-align: center; width: 35px;">Lp</th>
                                        <th style="padding: 8px 12px; text-align: left;">Produkt / Surowiec / Opakowanie</th>
                                        <th style="padding: 8px 12px; text-align: center; width: 120px;">Liczba Palet</th>
                                        <th style="padding: 8px 12px; text-align: right; width: 150px;">Łączna Ilość</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {transfers_products_rows}
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>

                <!-- Footer -->
                <div style="background: #f8fafc; padding: 18px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; text-align: center;">
                    Dzienny raport magazynowy wygenerowany automatycznie przez system RaportProdukcyjny. Do wiadomości dołączono oficjalne załączniki PDF do druku (raport zbiorczy oraz poszczególne dokumenty).
                </div>
            </div>
        </body>
        </html>
        """

    def generate_daily_summary_pdf(self, date_str: str, activity_data: Dict[str, Any]) -> Optional[str]:
        """Generuje plik PDF w układzie do druku A4 z pełnym zestawieniem dostaw i przesunięć z danego dnia (Zbiorczo + Dokumenty Osobno)."""
        deliveries = activity_data.get('deliveries', [])
        transfers = activity_data.get('transfers', [])
        total_pallets = activity_data.get('total_pallets', 0)
        total_qty_by_unit = activity_data.get('total_qty_by_unit', {})
        all_products = activity_data.get('all_products_summary', [])
        deliveries_products = activity_data.get('deliveries_products_summary', [])
        transfers_products = activity_data.get('transfers_products_summary', [])
        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        totals_str_parts = [f"{qty:,.2f} {unit}" for unit, qty in sorted(total_qty_by_unit.items())]
        totals_display = " | ".join(totals_str_parts) if totals_str_parts else "0 kg"

        # 1. ZBIORCZY REJESTR WSZYSTKICH POZYCJI RAZEM
        all_master_items = []
        for d in deliveries:
            for it in d.get('items', []):
                all_master_items.append({
                    'type_label': 'PZ',
                    'type_badge_bg': '#dbeafe',
                    'type_badge_color': '#1e40af',
                    'doc_ref': d.get('order_ref'),
                    'source': it.get('source_spot') or d.get('source'),
                    'target': it.get('target_spot') or d.get('destination'),
                    'created_by': d.get('created_by') or '-',
                    'accepted_by': d.get('accepted_by') or '-',
                    'product_name': it.get('product_name'),
                    'nr_palety': it.get('nr_palety'),
                    'nr_partii': it.get('nr_partii'),
                    'quantity': it.get('quantity'),
                    'unit': it.get('unit'),
                    'status': it.get('status'),
                    'accepted': it.get('accepted'),
                })
        for t in transfers:
            for it in t.get('items', []):
                all_master_items.append({
                    'type_label': 'MM',
                    'type_badge_bg': '#dcfce7',
                    'type_badge_color': '#166534',
                    'doc_ref': t.get('order_ref'),
                    'source': it.get('source_spot') or t.get('source'),
                    'target': it.get('target_spot') or t.get('destination'),
                    'created_by': t.get('created_by') or '-',
                    'accepted_by': t.get('accepted_by') or '-',
                    'product_name': it.get('product_name'),
                    'nr_palety': it.get('nr_palety'),
                    'nr_partii': it.get('nr_partii'),
                    'quantity': it.get('quantity'),
                    'unit': it.get('unit'),
                    'status': it.get('status'),
                    'accepted': it.get('accepted'),
                })

        master_rows_html = ""
        for m_idx, m in enumerate(all_master_items, start=1):
            st_color = "#166534" if m.get('accepted') else "#991b1b"
            master_rows_html += f"""
            <tr>
                <td style="text-align: center; font-weight: 700;">{m_idx}</td>
                <td style="text-align: center;"><span style="display: inline-block; padding: 1px 4px; border-radius: 3px; font-size: 7.5px; font-weight: 800; background: {m['type_badge_bg']}; color: {m['type_badge_color']};">{m['type_label']}</span></td>
                <td style="text-align: center; font-weight: 800; font-size: 7.5px;">{m.get('doc_ref')}</td>
                <td><strong>{m.get('product_name')}</strong></td>
                <td style="text-align: center; font-family: monospace; font-weight: 700; font-size: 7.5px;">{m.get('nr_palety')}</td>
                <td style="text-align: center; font-size: 7.5px;">{m.get('nr_partii')}</td>
                <td style="text-align: right; font-weight: 800; color: #166534;">{m.get('quantity'):,.2f} {m.get('unit')}</td>
                <td style="text-align: center; font-size: 7.5px;">{m.get('source')}</td>
                <td style="text-align: center; font-weight: 700; color: #1e40af; font-size: 7.5px;">{m.get('target')}</td>
                <td style="text-align: center; font-size: 7.5px; color: #334155;">{m.get('created_by')}</td>
                <td style="text-align: center; font-weight: 700; font-size: 7.5px; color: #166534;">{m.get('accepted_by')}</td>
                <td style="text-align: center; font-weight: 700; color: {st_color}; font-size: 7.5px;">{m.get('status')}</td>
            </tr>
            """

        def _render_pdf_doc_block(doc: Dict[str, Any], is_delivery: bool) -> str:
            src_label = "Dostawca" if is_delivery else "Skąd"
            dst_label = "Lokalizacja docelowa" if is_delivery else "Dokąd"
            header_bg = "#eff6ff" if is_delivery else "#f0fdf4"
            header_color = "#1e3a8a" if is_delivery else "#065f46"

            rows_html = ""
            for item in doc.get('items', []):
                status_txt = item.get('status', 'PRZYJĘTA')
                status_color = "#166534" if item.get('accepted') else "#991b1b"
                rows_html += f"""
                <tr>
                    <td style="text-align: center;">{item.get('lp')}</td>
                    <td><strong>{item.get('product_name')}</strong></td>
                    <td style="text-align: center; font-family: monospace; font-weight: 700;">{item.get('nr_palety')}</td>
                    <td style="text-align: center;">{item.get('nr_partii')}</td>
                    <td style="text-align: center;">{item.get('data_produkcji')}</td>
                    <td style="text-align: center;">{item.get('data_przydatnosci')}</td>
                    <td style="text-align: right; font-weight: 700;">{item.get('quantity'):,.2f} {item.get('unit')}</td>
                    <td style="text-align: center;">{item.get('source_spot')}</td>
                    <td style="text-align: center; font-weight: 700; color: #1e40af;">{item.get('target_spot')}</td>
                    <td style="text-align: center; font-weight: 700; color: {status_color};">{status_txt}</td>
                </tr>
                """

            return f"""
            <div class="doc-card">
                <div class="doc-card-head" style="background: {header_bg}; color: {header_color}; border-bottom: 1.5px solid {header_color};">
                    <div style="font-size: 13px; font-weight: 900;">{doc.get('doc_title')}: {doc.get('order_ref')}</div>
                    <div style="font-size: 10px; color: #475569;">
                        {src_label}: <strong>{doc.get('source')}</strong> ➔ {dst_label}: <strong>{doc.get('destination')}</strong> | 
                        Wprowadził: <strong>{doc.get('created_by')}</strong> | Przyjął: <strong>{doc.get('accepted_by')}</strong> ({doc.get('accepted_str')})
                    </div>
                </div>
                <div class="doc-card-body">
                    <table class="report-table">
                        <thead>
                            <tr>
                                <th style="width: 25px; text-align: center;">Lp</th>
                                <th style="text-align: left;">Produkt</th>
                                <th style="width: 80px; text-align: center;">Nr Palety</th>
                                <th style="width: 75px; text-align: center;">Partia</th>
                                <th style="width: 65px; text-align: center;">Data Prod.</th>
                                <th style="width: 65px; text-align: center;">Data Ważn.</th>
                                <th style="width: 75px; text-align: right;">Ilość</th>
                                <th style="width: 65px; text-align: center;">Skąd</th>
                                <th style="width: 70px; text-align: center;">Dokąd</th>
                                <th style="width: 65px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        deliv_blocks = "".join(_render_pdf_doc_block(d, is_delivery=True) for d in deliveries) if deliveries else '<p style="color: #64748b; font-style: italic; margin-bottom: 12px;">Brak dostaw zewnętrznych w tym dniu.</p>'
        transf_blocks = "".join(_render_pdf_doc_block(t, is_delivery=False) for t in transfers) if transfers else '<p style="color: #64748b; font-style: italic; margin-bottom: 12px;">Brak przesunięć wewnętrznych w tym dniu.</p>'

        def _render_pdf_products_rows(prod_list: List[Dict[str, Any]], count_color: str) -> str:
            if not prod_list:
                return '<tr><td colspan="4" style="text-align: center; color: #64748b; font-style: italic; padding: 6px;">Brak pozycji w tym zestawieniu.</td></tr>'
            rows = ""
            for idx, p in enumerate(prod_list, start=1):
                rows += f"""
                <tr>
                    <td style="text-align: center; width: 30px;">{idx}</td>
                    <td><strong>{p.get('product_name')}</strong></td>
                    <td style="text-align: center; font-weight: 700; color: {count_color}; width: 100px;">{p.get('count')} szt.</td>
                    <td style="text-align: right; font-weight: 800; color: #166534; width: 140px;">{p.get('total_qty'):,.2f} {p.get('unit')}</td>
                </tr>
                """
            return rows

        pdf_deliveries_products_rows = _render_pdf_products_rows(deliveries_products, "#1e3a8a")
        pdf_transfers_products_rows = _render_pdf_products_rows(transfers_products, "#065f46")

        html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="utf-8">
    <title>Zbiorczy Raport Magazynowy - {date_str}</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 12mm 10mm;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            color: #0f172a;
            margin: 0;
            padding: 0;
            font-size: 9.5px;
            line-height: 1.25;
        }}
        .header-box {{
            border: 2px solid #0f172a;
            border-radius: 6px;
            padding: 10px 14px;
            margin-bottom: 12px;
            background: #f8fafc;
        }}
        .doc-title {{
            font-size: 15px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 4px 0;
            color: #0f172a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .doc-meta {{
            font-size: 9.5px;
            color: #475569;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #cbd5e1;
            text-align: center;
        }}
        .kpi-item {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 6px;
        }}
        .kpi-label {{
            font-size: 8px;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
        }}
        .kpi-val {{
            font-size: 13px;
            font-weight: 900;
            color: #0f172a;
            margin-top: 2px;
        }}
        .section-title {{
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 14px 0 6px 0;
            padding-bottom: 3px;
            border-bottom: 1.5px solid #0f172a;
        }}
        .doc-card {{
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            margin-bottom: 10px;
            overflow: hidden;
            page-break-inside: avoid;
        }}
        .doc-card-head {{
            padding: 5px 8px;
        }}
        .doc-card-body {{
            padding: 5px 8px;
        }}
        table.report-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 8.5px;
            margin-top: 4px;
        }}
        table.report-table th, table.report-table td {{
            border: 1px solid #cbd5e1;
            padding: 3px 5px;
        }}
        table.report-table th {{
            background: #f1f5f9;
            font-weight: 800;
            text-transform: uppercase;
            font-size: 7.5px;
            color: #475569;
        }}
        .footer-note {{
            margin-top: 14px;
            font-size: 8px;
            color: #64748b;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 6px;
        }}
    </style>
</head>
<body>
    <div class="header-box">
        <div class="doc-title">
            <span>DZIENNY RAPORT ZBIORCZY: DOSTAWY I PRZESUNIĘCIA (MAGAZYN CENTRALNY)</span>
            <span style="font-size: 12px; color: #2563eb;">{date_str}</span>
        </div>
        <div class="doc-meta">
            Raport wygenerowano: <strong>{gen_now}</strong> | System RaportProdukcyjny (Magazyn Centralny)
        </div>
        <div class="kpi-grid">
            <div class="kpi-item">
                <div class="kpi-label">Dostawy PZ</div>
                <div class="kpi-val" style="color: #1e3a8a;">{len(deliveries)}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Przesunięcia MM</div>
                <div class="kpi-val" style="color: #065f46;">{len(transfers)}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Łącznie Palet</div>
                <div class="kpi-val" style="color: #0284c7;">{total_pallets}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Łączna Waga / Ilość</div>
                <div class="kpi-val" style="color: #166534; font-size: 11px;">{totals_display}</div>
            </div>
        </div>
    </div>

    <!-- SEKCJA 1: JEDNOLITY ZBIORCZY REJESTR WSZYSTKICH OPERACJI RAZEM -->
    <div class="section-title" style="color: #0f172a; border-bottom-color: #0f172a;">
        1. ZBIORCZY REJESTR WSZYSTKICH OPERACJI (DOSTAWY PZ I PRZESUNIĘCIA MM RAZEM) [{len(all_master_items)} palet]
    </div>
    <table class="report-table" style="margin-bottom: 14px;">
        <thead>
            <tr>
                <th style="width: 18px; text-align: center;">Lp</th>
                <th style="width: 24px; text-align: center;">Typ</th>
                <th style="width: 65px; text-align: center;">Dokument</th>
                <th style="text-align: left;">Produkt / Surowiec</th>
                <th style="width: 78px; text-align: center;">Nr Palety (SSCC)</th>
                <th style="width: 55px; text-align: center;">Partia</th>
                <th style="width: 60px; text-align: right;">Ilość</th>
                <th style="width: 45px; text-align: center;">Skąd</th>
                <th style="width: 50px; text-align: center;">Dokąd</th>
                <th style="width: 52px; text-align: center;">Wydał</th>
                <th style="width: 52px; text-align: center;">Przyjął</th>
                <th style="width: 48px; text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            {master_rows_html}
        </tbody>
    </table>

    <!-- SEKCJA 2.1: DOSTAWY ZEWNĘTRZNE OSOBNO -->
    <div class="section-title" style="color: #1e3a8a; border-bottom-color: #1e3a8a; page-break-before: auto;">
        2.1. SZCZEGÓŁOWE KARTY: PRZYJĘCIA DOSTAW (PZ) [{len(deliveries)}]
    </div>
    {deliv_blocks}

    <!-- SEKCJA 2.2: PRZESUNIĘCIA MM OSOBNO -->
    <div class="section-title" style="color: #065f46; border-bottom-color: #065f46;">
        2.2. SZCZEGÓŁOWE KARTY: PRZESUNIĘCIA MM I TRANSFERY WEWNĘTRZNE [{len(transfers)}]
    </div>
    {transf_blocks}

    <!-- SEKCJA 3: PODSUMOWANIE ASORTYMENTU -->
    <div class="section-title" style="color: #1e3a8a; border-bottom-color: #1e3a8a;">
        3.1. ZBIORCZE PODSUMOWANIE ASORTYMENTU: PRZYJĘCIA DOSTAW (PZ) [{len(deliveries_products)}]
    </div>
    <table class="report-table" style="margin-bottom: 12px; page-break-inside: avoid;">
        <thead>
            <tr>
                <th style="width: 30px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt / Surowiec / Opakowanie</th>
                <th style="width: 100px; text-align: center;">Liczba Palet</th>
                <th style="width: 140px; text-align: right;">Łączna Ilość</th>
            </tr>
        </thead>
        <tbody>
            {pdf_deliveries_products_rows}
        </tbody>
    </table>

    <div class="section-title" style="color: #065f46; border-bottom-color: #065f46;">
        3.2. ZBIORCZE PODSUMOWANIE ASORTYMENTU: PRZESUNIĘCIA MM I TRANSFERY WEWNĘTRZNE [{len(transfers_products)}]
    </div>
    <table class="report-table" style="margin-bottom: 12px; page-break-inside: avoid;">
        <thead>
            <tr>
                <th style="width: 30px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt / Surowiec / Opakowanie</th>
                <th style="width: 100px; text-align: center;">Liczba Palet</th>
                <th style="width: 140px; text-align: right;">Łączna Ilość</th>
            </tr>
        </thead>
        <tbody>
            {pdf_transfers_products_rows}
        </tbody>
    </table>

    <div class="footer-note">
        Dokument wygenerowany automatycznie z bazy danych systemu RaportProdukcyjny. Zawiera rejestr zbiorczy oraz szczegółowe zestawienie wszystkich zatwierdzonych operacji z dnia {date_str}.
    </div>
</body>
</html>
        """
        return self._render_html_to_temp_pdf(html_content, prefix=f"raport_dzienny_{date_str}_")

    def send_daily_warehouse_summary_report(self, date_str: Optional[str] = None, force: bool = False) -> Tuple[bool, str]:
        """
        Wysyła dzienny zbiorczy raport z dostaw i przesunięć z danego dnia na listę odbiorców.
        Załącza główny raport zbiorczy (wszystko razem) oraz opcjonalnie/dodatkowo każdy dokument WZ i MM z osobna.
        Jeśli w danym dniu nie było dostaw ani przesunięć i nie wymuszono wysyłki (force=False), raport nie jest wysyłany.
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        dispatch_key = f"daily_summary_{date_str}"
        with self._dispatch_lock:
            if not force and date_str in self._sent_daily_dates:
                return False, f"Zbiorczy raport dzienny dla {date_str} został już wysłany w tej sesji aplikacji."
            if dispatch_key in self._active_dispatches:
                return False, f"Wysyłka raportu dziennego dla {date_str} jest już w toku."
            self._active_dispatches.add(dispatch_key)

        try:
            config = self.settings_repo.get_settings()
            if not config.is_active:
                return False, "Moduł wysyłki e-mail jest wyłączony w ustawieniach."

            if not config.is_configured:
                return False, "Dedykowane konto e-mail nadawcy nie zostało jeszcze skonfigurowane."

            recipients = config.recipients_list
            if not recipients:
                return False, "Brak zdefiniowanych adresów e-mail odbiorców w Ustawieniach E-mail."

            activity_data = self.get_daily_warehouse_activity(date_str)
            if not activity_data['has_activity'] and not force:
                return False, f"Brak zarejestrowanych dostaw i przesunięć w dniu {date_str} - raport nie został wysłany."

            subject = f"📋 Raport Dzienny Przyjęć PZ i Przesunięć MM (Magazyn Centralny): {date_str} (Dostawy PZ: {activity_data['deliveries_count']}, MM: {activity_data['transfers_count']}, Palety: {activity_data['total_pallets']})"
            body_html = self.build_daily_summary_report_html(date_str, activity_data)

            temp_pdf_files = []
            attachments = []
            try:
                # 1. Główny załącznik zbiorczy (wszystkie przesunięcia i dostawy razem na jednym wydruku)
                pdf_summary_path = self.generate_daily_summary_pdf(date_str, activity_data)
                if pdf_summary_path and os.path.exists(pdf_summary_path):
                    temp_pdf_files.append(pdf_summary_path)
                    attachments.append((pdf_summary_path, f"Raport_Zbiorczy_Magazyn_Centralny_{date_str}.pdf"))

                # 2. Załączniki z każdego przesunięcia i dostawy osobno
                for d in activity_data.get('deliveries', []):
                    ref_clean = re.sub(r'[^A-Za-z0-9_-]', '_', str(d.get('order_ref') or 'PZ'))
                    d_doc = {
                        'id': d.get('id'),
                        'order_ref': d.get('order_ref'),
                        'supplier': d.get('source'),
                        'lokalizacja_z': d.get('source'),
                        'lokalizacja_do': d.get('destination'),
                        'created_by': d.get('created_by'),
                        'potwierdzone_przez': d.get('accepted_by'),
                        'uwagi': d.get('uwagi')
                    }
                    pdf_d = self.generate_delivery_pdf(d_doc, d.get('items', []))
                    if pdf_d and os.path.exists(pdf_d):
                        temp_pdf_files.append(pdf_d)
                        attachments.append((pdf_d, f"Dostawa_PZ_{ref_clean}.pdf"))

                for t in activity_data.get('transfers', []):
                    ref_clean = re.sub(r'[^A-Za-z0-9_-]', '_', str(t.get('order_ref') or 'MM'))
                    t_doc = {
                        'id': t.get('id'),
                        'order_ref': t.get('order_ref'),
                        'lokalizacja_z': t.get('source'),
                        'lokalizacja_do': t.get('destination'),
                        'created_by': t.get('created_by'),
                        'potwierdzone_przez': t.get('accepted_by'),
                        'uwagi': t.get('uwagi')
                    }
                    pdf_t = self.generate_delivery_pdf(t_doc, t.get('items', []))
                    if pdf_t and os.path.exists(pdf_t):
                        temp_pdf_files.append(pdf_t)
                        attachments.append((pdf_t, f"Przesuniecie_MM_{ref_clean}.pdf"))

                ok, msg = self._send_raw_email(config, recipients, subject, body_html, attachments=attachments)
                if ok:
                    with self._dispatch_lock:
                        self._sent_daily_dates.add(date_str)
                    try:
                        self.settings_repo.update_last_daily_report_date(date_str)
                    except Exception as db_err:
                        print(f"[DAILY_REPORT_EMAIL] Ostrzeżenie zapisu last_daily_report_date w bazie: {db_err}")
                    return True, f"Zbiorczy raport dzienny za dzień {date_str} wysłany pomyślnie z załącznikami ({len(attachments)} plików PDF) na adresy: {', '.join(recipients)}."
                return ok, msg
            finally:
                for p in temp_pdf_files:
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
        finally:
            with self._dispatch_lock:
                self._active_dispatches.discard(dispatch_key)

    @classmethod
    def trigger_async_daily_warehouse_report(cls, date_str: Optional[str] = None, force: bool = False) -> None:
        """Uruchamia w osobnym wątku wysyłkę dziennego raportu zbiorczego."""
        def _worker():
            try:
                service = cls()
                ok, msg = service.send_daily_warehouse_summary_report(date_str=date_str, force=force)
                if ok:
                    print(f"[DAILY_REPORT_EMAIL] Sukces wysyłki raportu dziennego ({date_str}): {msg}")
                else:
                    print(f"[DAILY_REPORT_EMAIL] Informacja o raporcie dziennym ({date_str}): {msg}")
            except Exception as ex:
                print(f"[DAILY_REPORT_EMAIL] Błąd krytyczny wysyłki raportu dziennego: {ex}")

        threading.Thread(target=_worker, daemon=True).start()

    @classmethod
    def trigger_async_delivery_report(cls, dostawa_id: Any) -> None:
        """Kompatybilność wsteczna: uruchamia ręczną/wymuszoną wysyłkę e-mail po przyjęciu dostawy."""
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

    @classmethod
    def trigger_async_transfer_report(cls, transfer_id: Any) -> None:
        """Kompatybilność wsteczna: uruchamia ręczną/wymuszoną wysyłkę e-mail po przyjęciu transferu OSIP."""
        if not transfer_id:
            return
        def _worker():
            try:
                service = cls()
                ok, msg = service.send_osip_transfer_report(transfer_id)
                print(f"[OSIP_EMAIL] Wynik wysyłki dla transferu {transfer_id}: {msg}")
            except Exception as ex:
                print(f"[OSIP_EMAIL] Błąd wysyłki dla transferu {transfer_id}: {ex}")

        threading.Thread(target=_worker, daemon=True).start()

