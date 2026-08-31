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
    
    _active_dispatches: Set[str] = set()
    _dispatch_lock: threading.Lock = threading.Lock()

    def __init__(self, settings_repo: Optional[OsipEmailSettingsRepository] = None):
        self.settings_repo = settings_repo or OsipEmailSettingsRepository()

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

        is_external = bool(supplier) or not source_loc
        is_dest_osip = cls._is_osip_location(dest_loc) or any(cls._is_osip_location(it.get('lokalizacja_przyjecia') or it.get('targetSpot')) for it in items)
        is_source_osip = cls._is_osip_location(source_loc)

        if is_external:
            if is_dest_osip:
                doc_type_code = 'DOSTAWA_OSIP'
                doc_title = 'Dostawa OSIP'
                header_title = '🚚 Raport Przyjęcia: Dostawa OSIP'
                theme_color_from = '#581c87'
                theme_color_to = '#7e22ce'
                source_label = 'DOSTAWCA'
                source_value = supplier or 'Dostawca zewnętrzny'
                dest_label = 'MAGAZYN DOCELOWY (OSIP)'
                dest_value = dest_loc or 'OSIP'
                creator_label = 'OTWORZYŁ / WPROWADZIŁ'
                acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
                subject_tag = 'Dostawa OSIP'
            else:
                doc_type_code = 'DOSTAWA_CENTRALA'
                doc_title = 'Dostawa Centrala'
                header_title = '🏢 Raport Przyjęcia: Dostawa Centrala'
                theme_color_from = '#1e3a8a'
                theme_color_to = '#2563eb'
                source_label = 'DOSTAWCA'
                source_value = supplier or 'Dostawca zewnętrzny'
                dest_label = 'LOKALIZACJA DOCELOWA'
                dest_value = dest_loc or 'Centrala / Magazyn Główny'
                creator_label = 'OTWORZYŁ / WPROWADZIŁ'
                acceptor_label = 'PRZYJĄŁ / ZATWIERDZIŁ'
                subject_tag = 'Dostawa Centrala'
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
                for file_path in attachments:
                    if file_path and os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
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
        for idx, it in enumerate(items, start=1):
            prod = getattr(it, 'product_name', None) or (it.get('product_name') if isinstance(it, dict) else 'Brak nazwy')
            nr_pal = getattr(it, 'nr_palety', None) or (it.get('nr_palety') if isinstance(it, dict) else '-')
            batch = getattr(it, 'batch_number', None) or (it.get('batch_number') if isinstance(it, dict) else '-')
            qty = float(getattr(it, 'loaded_qty', 0.0) or getattr(it, 'requested_qty', 0.0) or (it.get('loaded_qty', 0.0) if isinstance(it, dict) else it.get('requested_qty', 0.0)) or 0.0)
            unit = getattr(it, 'unit', 'kg') or (it.get('unit', 'kg') if isinstance(it, dict) else 'kg')
            it_status = getattr(it, 'status', 'RECEIVED') or (it.get('status') if isinstance(it, dict) else 'RECEIVED')
            total_qty += qty

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

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, #1e1b4b, #4338ca); padding: 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">Raport Przyjęcia Transferu Towaru</div>
                    <div style="font-size: 22px; font-weight: 900; margin-top: 4px;">🚚 Transfer: {source} ➔ {dest}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Kod zlecenia: <strong>{code}</strong> | Status: <strong>PRZYJĘTE ({status})</strong></div>
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

                <div style="padding: 24px;">
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
            total_qty += qty

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

                <div style="padding: 24px;">
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
        for idx, it in enumerate(items, start=1):
            pname = it.get('productName') or 'Brak nazwy'
            nr_pal = it.get('nr_palety') or '-'
            nr_partii = it.get('nr_partii') or '-'
            prod_date = it.get('data_produkcji') or '-'
            exp_date = it.get('data_przydatnosci') or '-'
            raw_q = it.get('quantity') or it.get('netWeight') or it.get('unitsPerPallet') or 0
            try:
                qty = float(raw_q)
            except Exception:
                qty = 0.0
            unit = 'szt' if it.get('packageForm') == 'packaging' else 'kg'
            source_spot = it.get('sourceSpot') or cat['source_value']
            target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
            accepted = bool(it.get('accepted'))
            status_txt = "PRZYJĘTA" if accepted else "ODRZUCONA"
            status_color = "#166534" if accepted else "#991b1b"
            total_qty += qty

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

        doc_title = f"Transfer: {source} ➔ {dest}"
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
            <span style="color: #2563eb;">KOD: {code}</span>
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

    <div class="summary-box">
        <div>ŁĄCZNIE PRZYJĘTO PALET: <span style="color: #2563eb;">{total_pallets} szt.</span></div>
        <div>SUMA ILOŚCI TOWARU: <span style="color: #166534;">{total_qty:,.2f}</span></div>
    </div>

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
            
            subject = f"[Transfer: {source} ➔ {dest}] Zlecenie {code}"
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
            tag = cat['subject_tag']

            subject = f"[{tag}] WZ/Nr: {ref} ({source_val} ➔ {dest_val})"
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

    @classmethod
    def trigger_async_delivery_report(cls, dostawa_id: Any) -> None:
        """Uruchamia asynchroniczną wysyłkę e-mail po przyjęciu dostawy lub przesunięcia MM."""
        if not dostawa_id:
            return
        try:
            from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
            cfg = OsipEmailSettingsRepository().get_settings()
            if not (cfg.is_active and cfg.auto_send_on_dispatch):
                return

            # Wczesne sprawdzenie czy wysyłka nie jest już w toku lub już zrealizowana
            dispatch_key = f"delivery_{dostawa_id}"
            with cls._dispatch_lock:
                if dispatch_key in cls._active_dispatches:
                    return

            def _worker():
                try:
                    service = cls()
                    ok, msg = service.send_central_delivery_osip_report(dostawa_id)
                    if ok:
                        print(f"[WAREHOUSE_EMAIL] Sukces wysyłki e-mail dla dostawy {dostawa_id}: {msg}")
                    else:
                        print(f"[WAREHOUSE_EMAIL] Informacja dla dostawy {dostawa_id}: {msg}")
                except Exception as ex:
                    print(f"[WAREHOUSE_EMAIL] Błąd krytyczny wysyłki e-mail dla dostawy {dostawa_id}: {ex}")

            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            print(f"[WAREHOUSE_EMAIL] Błąd inicjalizacji wątku e-mail dla dostawy {dostawa_id}: {e}")

    @classmethod
    def trigger_async_transfer_report(cls, transfer_id: Any) -> None:
        """Uruchamia asynchroniczną wysyłkę e-mail po przyjęciu transferu OSIP."""
        if not transfer_id:
            return
        try:
            from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
            cfg = OsipEmailSettingsRepository().get_settings()
            if not (cfg.is_active and cfg.auto_send_on_dispatch):
                return

            dispatch_key = f"transfer_{transfer_id}"
            with cls._dispatch_lock:
                if dispatch_key in cls._active_dispatches:
                    return

            def _worker():
                try:
                    service = cls()
                    ok, msg = service.send_osip_transfer_report(transfer_id)
                    if ok:
                        print(f"[OSIP_EMAIL] Sukces wysyłki e-mail dla transferu {transfer_id}: {msg}")
                    else:
                        print(f"[OSIP_EMAIL] Informacja dla transferu {transfer_id}: {msg}")
                except Exception as ex:
                    print(f"[OSIP_EMAIL] Błąd krytyczny wysyłki e-mail dla transferu {transfer_id}: {ex}")

            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            print(f"[OSIP_EMAIL] Błąd inicjalizacji wątku e-mail dla transferu {transfer_id}: {e}")
