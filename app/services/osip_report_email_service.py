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
from email.header import Header
from email import encoders
from typing import List, Optional, Tuple, Dict, Any, Set, Union
from datetime import datetime

from app.core.database import get_db_connection
from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
from app.models.osip_email_settings_model import OsipEmailSettingsModel


class OsipReportEmailService:
    """Obsługa wysyłki raportów dostaw, przesunięć MM i transferów z dedykowanego konta pocztowego."""

    OSIP_LOCATION_KEYWORDS = ('OSIP', 'OS01', 'OS02', 'OS03', 'OS04', 'OS05', 'OS06', 'OS07', 'OS08', 'OS09', 'W_TRANZYCIE_OSIP')
    
    _active_dispatches: Set[str] = set()
    _sent_daily_dates: Set[str] = set()
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
    def _is_rack_location(cls, loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja jest regałem magazynowym (np. R010101, R090201, R220101)."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        if re.match(r'^R\d{2}', l):
            return True
        if any(k in l for k in ('REGAL', 'REGAŁ', 'REG_')):
            return True
        return False

    @classmethod
    def _is_mp01_location(cls, loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja należy do strefy MP01 (podłoga, bufor lub regały R01-R03)."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        if l in ('MP01', 'BF_MP01', 'BFMP01', 'PODŁOGA MP01', 'PODLOGA MP01'):
            return True
        if re.match(r'^R0[1-3]', l):
            return True
        return False

    @classmethod
    def _extract_item_qty(cls, item: Dict[str, Any]) -> float:
        """
        Pobiera rzeczywistą wagę/ilość pozycji, priorytetowo traktując wagę netto (netWeight),
        np. po podziale palety lub ponownym przeważyceniu towaru.
        """
        if not isinstance(item, dict):
            return 0.0

        net_w = item.get('netWeight')
        if net_w not in (None, '', 0, '0'):
            try:
                return float(net_w)
            except (ValueError, TypeError):
                pass

        for k in ('quantity', 'unitsPerPallet', 'ilosc', 'loaded_qty', 'requested_qty'):
            val = item.get(k)
            if val not in (None, '', 0, '0'):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
        return 0.0

    @classmethod
    def _is_production_zone(cls, loc: Optional[str]) -> bool:
        """Sprawdza czy lokalizacja wskazuje na strefę produkcyjną."""
        if not loc:
            return False
        l = str(loc).strip().upper()
        if 'PRODUKCJA' in l or 'PROD' in l:
            return True
        if any(k in l for k in ('ZASYP', 'WORKOWANIE', 'STACJA', 'LP01')):
            return True
        return False

    @classmethod
    def is_production_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Weryfikuje czy dokument dotyczy przesunięcia z produkcji (odrzucany z raportu przesunięć magazynowych)."""
        supplier = str(dostawa.get('supplier') or '').strip().upper()
        if 'PRODUKCJA' in supplier or supplier.startswith('PROD'):
            return True

        src = str(dostawa.get('lokalizacja_z') or '').strip().upper()
        if cls._is_production_zone(src):
            return True

        ref = str(dostawa.get('order_ref') or '').strip().lower()
        if any(ref.startswith(k) for k in ('czyszczenie', 'zwrot ze stacji', 'zlecenie #', 'zlecenie_')):
            return True

        if items and isinstance(items, list):
            valid_items = [it for it in items if isinstance(it, dict)]
            if valid_items:
                if any(it.get('is_return') for it in valid_items):
                    return True
                if all(cls._is_production_zone(it.get('sourceSpot') or it.get('source_location')) for it in valid_items):
                    return True

        return False

    @classmethod
    def is_internal_mp01_movement(cls, dostawa: Dict[str, Any], items: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Weryfikuje czy ruch odbywa się wewnątrz strefy magazynowej / regałów (relokacje wewnętrzne odrzucane z MM):
        - z regału na MP01 (np. R090201 -> MP01)
        - z MP01 na regał (np. MP01 -> R010101)
        - między regałami (np. R090401 -> R090201)
        - z produkcji na MP01 (np. PRODUKCJA -> MP01)
        - wewnątrz MP01 (np. podłoga MP01 -> bufor MP01)
        """
        src = str(dostawa.get('lokalizacja_z') or '').strip().upper()
        dest = str(dostawa.get('lokalizacja_do') or '').strip().upper()

        actual_sources = []
        actual_targets = []
        if items and isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    s = str(it.get('sourceSpot') or it.get('source_location') or it.get('lokalizacja_z') or '').strip().upper()
                    t = str(it.get('lokalizacja_przyjecia') or it.get('targetSpot') or it.get('lokalizacja_do') or '').strip().upper()
                    if s and s not in ('DOSTAWA', 'WIELE'):
                        actual_sources.append(s)
                    if t and t not in ('OCZEKUJĄCE', 'WIELE'):
                        actual_targets.append(t)

        # 1. Z produkcji na MP01
        is_src_prod = cls._is_production_zone(src) or (actual_sources and any(cls._is_production_zone(s) for s in actual_sources))
        is_dest_mp01 = cls._is_mp01_location(dest) or (actual_targets and any(cls._is_mp01_location(t) for t in actual_targets))
        if is_src_prod and is_dest_mp01:
            return True

        # 2. Z regału na MP01 (np. R090201 -> MP01 lub WIELE(R090201) -> MP01)
        is_src_rack = cls._is_rack_location(src) or (actual_sources and all(cls._is_rack_location(s) for s in actual_sources))
        if is_src_rack and is_dest_mp01:
            return True

        # 3. Z MP01 na regał (np. MP01 -> R010101 lub MP01 -> WIELE(R...))
        is_src_mp01 = cls._is_mp01_location(src) or (actual_sources and all(cls._is_mp01_location(s) for s in actual_sources))
        is_dest_rack = cls._is_rack_location(dest) or (actual_targets and all(cls._is_rack_location(t) for t in actual_targets))
        if is_src_mp01 and is_dest_rack:
            return True

        # 4. Wewnątrz MP01 (podłoga/bufor MP01 -> MP01)
        if is_src_mp01 and is_dest_mp01:
            return True

        # 5. Między regałami
        if is_src_rack and is_dest_rack:
            return True

        return False

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
        attachments: Optional[List[Union[str, Tuple[str, str]]]] = None
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
            msg['Subject'] = Header(subject, 'utf-8').encode()

            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            if attachments:
                for item in attachments:
                    if isinstance(item, (tuple, list)) and len(item) == 2:
                        file_path, display_name = item[0], item[1]
                    else:
                        file_path = str(item)
                        display_name = os.path.basename(file_path)

                    if file_path and os.path.exists(file_path):
                        clean_filename = re.sub(r'[\r\n/\\:*?"<>|]', '_', str(display_name))
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'pdf' if clean_filename.lower().endswith('.pdf') else 'octet-stream')
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{clean_filename}"')
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
            qty = self._extract_item_qty(it)
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
            pname = it.get('productName') or 'Brak nazwy'
            nr_pal = it.get('nr_palety') or '-'
            nr_partii = it.get('nr_partii') or '-'
            prod_date = it.get('data_produkcji') or '-'
            exp_date = it.get('data_przydatnosci') or '-'
            qty = self._extract_item_qty(it)
            unit = 'szt' if it.get('packageForm') == 'packaging' else 'kg'
            source_spot = it.get('sourceSpot') or cat['source_value']
            target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
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
        def _get_val(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        code = _get_val(transfer, 'transfer_code', '') or f"TR-{_get_val(transfer, 'id', '')}"
        source = _get_val(transfer, 'source_warehouse', '') or 'Centrala'
        dest = _get_val(transfer, 'destination_warehouse', '') or 'OSIP'
        created_by = _get_val(transfer, 'created_by', '') or _get_val(transfer, 'dispatched_by', '') or 'System'
        completed_by = _get_val(transfer, 'completed_by', None) or _get_val(transfer, 'updated_by', None) or '-'
        
        created_at = _get_val(transfer, 'created_at', None)
        completed_at = _get_val(transfer, 'completed_at', None) or _get_val(transfer, 'updated_at', None) or created_at
        
        created_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at and hasattr(created_at, 'strftime') else (str(created_at) if created_at else '-')
        completed_str = completed_at.strftime('%Y-%m-%d %H:%M') if completed_at and hasattr(completed_at, 'strftime') else (str(completed_at) if completed_at else '-')
        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        raw_items = transfer.get('items', []) if isinstance(transfer, dict) else (getattr(transfer, 'items', []) or [])
        items = raw_items if isinstance(raw_items, list) else []

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        summary_products = {}
        for idx, it in enumerate(items, start=1):
            pname = _get_val(it, 'product_name') or _get_val(it, 'productName') or 'Brak nazwy'
            nr_pal = _get_val(it, 'nr_palety') or '-'
            batch = _get_val(it, 'batch_number') or _get_val(it, 'nr_partii') or '-'
            prod_date = _get_val(it, 'production_date') or _get_val(it, 'data_produkcji') or '-'
            exp_date = _get_val(it, 'expiry_date') or _get_val(it, 'data_przydatnosci') or '-'
            raw_q = _get_val(it, 'loaded_qty') or _get_val(it, 'requested_qty') or _get_val(it, 'quantity') or 0
            try:
                qty = float(raw_q or 0)
            except Exception:
                qty = 0.0
            unit = _get_val(it, 'unit') or 'kg'
            loc = _get_val(it, 'target_location') or _get_val(it, 'targetSpot') or dest
            status_txt = _get_val(it, 'status') or 'RECEIVED'
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

            # Zgodnie z regułami biznesowymi: nie wysyłamy raportów z ruchów produkcyjnych ani wewnątrz MP01
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

    def get_daily_warehouse_activity(self, date_str: str) -> Dict[str, Any]:
        """
        Pobiera wszystkie zrealizowane w danym dniu dostawy zewnętrzne oraz przesunięcia MM / transfery.
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

            # 2. Pobierz transfery z osip_transfers
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
                cursor.close()
        finally:
            conn.close()

        deliveries_wz = []
        deliveries_centrala = []
        transfers_mm = []
        all_documents = []

        deliveries_wz_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        deliveries_centrala_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        transfers_mm_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        all_products_summary: Dict[Tuple[str, str], Dict[str, Any]] = {}
        total_pallets = 0
        total_qty_by_unit: Dict[str, float] = {}

        # Przetwarzanie magazyn_dostawy
        for d in dostawy_rows:
            try:
                raw_items = json.loads(d.get('items') or '[]')
            except Exception:
                raw_items = []

            # 1. Zgodnie z wymaganiami: wykluczamy przesunięcia z produkcji
            if self.is_production_movement(d, raw_items):
                continue

            # 2. Wykluczamy przesunięcia wewnątrz MP01 (np. z podłogi MP01 na regały R01-R03) oraz z produkcji na MP01
            if self.is_internal_mp01_movement(d, raw_items):
                continue

            cat = self.categorize_delivery_doc(d, raw_items)
            supplier_val = str(d.get('supplier') or '').strip()
            supplier_upper = supplier_val.upper()
            src_upper = str(d.get('lokalizacja_z') or '').strip().upper()
            ref_val = cat['ref']
            clean_ref = re.sub(r'[\s/\\:*?"<>|]+', '_', str(ref_val)).strip('_')

            # Podział na 3 typy wymagane przez użytkownika:
            # - Przesunięcia MM (ruch międzymagazynowy bez dostawcy zewnętrznego)
            # - Dostawa Centrala (dostawca to Centrala lub dostawa do/z Centrali)
            # - Dostawy Zewnętrzne (WZ) (dostawy od zewnętrznych kontrahentów)
            if not cat['is_external']:
                doc_category = 'PRZESUNIECIE_MM'
                doc_category_title = 'Przesunięcie MM'
                pdf_filename = f"Przesuniecie_MM_{clean_ref}.pdf"
            elif supplier_upper in ('CENTRALA', 'MAGAZYN CENTRALA', 'MAGAZYN CENTRALNY') or src_upper in ('CENTRALA', 'MAGAZYN CENTRALA'):
                doc_category = 'DOSTAWA_CENTRALA'
                doc_category_title = 'Dostawa Centrala'
                pdf_filename = f"Dostawa_Centrala_{clean_ref}.pdf"
            elif cat['doc_type_code'] == 'DOSTAWA_CENTRALA':
                if not supplier_val or supplier_upper in ('CENTRALA', 'MAGAZYN CENTRALA', 'MAGAZYN CENTRALNY'):
                    doc_category = 'DOSTAWA_CENTRALA'
                    doc_category_title = 'Dostawa Centrala'
                    pdf_filename = f"Dostawa_Centrala_{clean_ref}.pdf"
                else:
                    doc_category = 'DOSTAWA_ZEWNETRZNA'
                    doc_category_title = 'Dostawa Zewnętrzna (WZ)'
                    pdf_filename = f"Dostawa_WZ_{clean_ref}.pdf"
            else:
                doc_category = 'DOSTAWA_ZEWNETRZNA'
                doc_category_title = 'Dostawa Zewnętrzna (WZ)'
                pdf_filename = f"Dostawa_WZ_{clean_ref}.pdf"

            doc_items = []
            doc_summary_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for idx, it in enumerate(raw_items, start=1):
                pname_raw = it.get('productName') or 'Brak nazwy'
                pname = re.sub(r'\s+', ' ', str(pname_raw).strip())
                nr_pal = it.get('nr_palety') or '-'
                nr_partii = it.get('nr_partii') or '-'
                prod_date = it.get('data_produkcji') or '-'
                exp_date = it.get('data_przydatnosci') or '-'
                qty = self._extract_item_qty(it)
                unit = ('szt' if it.get('packageForm') == 'packaging' else 'kg').strip().lower()
                source_spot = it.get('sourceSpot') or cat['source_value']
                target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
                accepted = bool(it.get('accepted'))
                status_txt = "PRZYJĘTA" if accepted else "ODRZUCONA"

                item_obj = {
                    'lp': idx,
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

                # Statystyki dedykowane per kategoria
                if doc_category == 'DOSTAWA_ZEWNETRZNA':
                    target_summary = deliveries_wz_products_summary
                elif doc_category == 'DOSTAWA_CENTRALA':
                    target_summary = deliveries_centrala_products_summary
                else:
                    target_summary = transfers_mm_products_summary

                if s_key not in target_summary:
                    target_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                target_summary[s_key]['count'] += 1
                target_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            doc_entry = {
                'id': d.get('id'),
                'order_ref': cat['ref'],
                'doc_type': doc_category,
                'category': doc_category,
                'doc_title': doc_category_title,
                'source': cat['source_value'],
                'destination': cat['dest_value'],
                'created_by': cat['created_by'],
                'created_str': cat['created_str'],
                'accepted_by': cat['accepted_by'],
                'accepted_str': cat['accepted_str'],
                'uwagi': d.get('uwagi') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values()),
                'pdf_filename': pdf_filename,
                'raw_dostawa': d,
                'raw_items': raw_items,
                'raw_transfer': None
            }

            if doc_category == 'DOSTAWA_ZEWNETRZNA':
                deliveries_wz.append(doc_entry)
            elif doc_category == 'DOSTAWA_CENTRALA':
                deliveries_centrala.append(doc_entry)
            else:
                transfers_mm.append(doc_entry)

            all_documents.append(doc_entry)

        # Przetwarzanie osip_transfers (zlecenia transferów międzymagazynowych Centrala <-> OSIP)
        for tr in osip_transfers_rows:
            tr_id = tr.get('id')
            raw_t_items = osip_items_by_transfer.get(tr_id, [])
            code = tr.get('transfer_code') or f"TR-{tr_id}"
            clean_code = re.sub(r'[\s/\\:*?"<>|]+', '_', str(code)).strip('_')
            source = tr.get('source_warehouse') or 'Centrala'
            dest = tr.get('destination_warehouse') or 'OSIP'

            # Wyklucz strefy produkcyjne
            if self._is_production_zone(source) or self._is_production_zone(dest):
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

                if s_key not in transfers_mm_products_summary:
                    transfers_mm_products_summary[s_key] = {'product_name': pname, 'unit': unit, 'count': 0, 'total_qty': 0.0}
                transfers_mm_products_summary[s_key]['count'] += 1
                transfers_mm_products_summary[s_key]['total_qty'] += qty

                total_qty_by_unit[unit] = total_qty_by_unit.get(unit, 0.0) + qty
                total_pallets += 1

            pdf_filename = f"Przesuniecie_MM_{clean_code}.pdf"
            doc_entry = {
                'id': tr_id,
                'order_ref': code,
                'doc_type': 'TRANSFER_OSIP',
                'category': 'PRZESUNIECIE_MM',
                'doc_title': f'Przesunięcie MM ({source} ➔ {dest})',
                'source': source,
                'destination': dest,
                'created_by': created_by,
                'created_str': created_str,
                'accepted_by': completed_by,
                'accepted_str': completed_str,
                'uwagi': tr.get('notes') or '-',
                'items': doc_items,
                'items_count': len(doc_items),
                'summary': list(doc_summary_map.values()),
                'pdf_filename': pdf_filename,
                'raw_dostawa': None,
                'raw_transfer': tr,
                'raw_items': raw_t_items
            }
            transfers_mm.append(doc_entry)
            all_documents.append(doc_entry)

        has_activity = bool(all_documents)
        legacy_deliveries_products = list(deliveries_wz_products_summary.values()) + list(deliveries_centrala_products_summary.values())

        return {
            'date_str': date_str,
            'deliveries_wz': deliveries_wz,
            'deliveries_centrala': deliveries_centrala,
            'transfers_mm': transfers_mm,
            'all_documents': all_documents,
            'deliveries_wz_count': len(deliveries_wz),
            'deliveries_centrala_count': len(deliveries_centrala),
            'transfers_mm_count': len(transfers_mm),
            'all_documents_count': len(all_documents),
            # Kompatybilność wsteczna:
            'deliveries': deliveries_wz + deliveries_centrala,
            'transfers': transfers_mm,
            'deliveries_count': len(deliveries_wz) + len(deliveries_centrala),
            'transfers_count': len(transfers_mm),
            'total_pallets': total_pallets,
            'total_qty_by_unit': total_qty_by_unit,
            'deliveries_wz_products_summary': sorted(deliveries_wz_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'deliveries_centrala_products_summary': sorted(deliveries_centrala_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'transfers_mm_products_summary': sorted(transfers_mm_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'deliveries_products_summary': sorted(legacy_deliveries_products, key=lambda x: x['product_name'].lower()),
            'all_products_summary': sorted(all_products_summary.values(), key=lambda x: x['product_name'].lower()),
            'has_activity': has_activity
        }

    def build_daily_summary_report_html(self, date_str: str, activity_data: Dict[str, Any]) -> str:
        """Buduje raport HTML z podsumowaniem dnia z wyraźnym podziałem na Dostawy WZ, Centrala i Przesunięcia MM."""
        deliveries_wz = activity_data.get('deliveries_wz', [])
        deliveries_centrala = activity_data.get('deliveries_centrala', [])
        transfers_mm = activity_data.get('transfers_mm', [])
        all_documents = activity_data.get('all_documents', [])

        total_pallets = activity_data.get('total_pallets', 0)
        total_qty_by_unit = activity_data.get('total_qty_by_unit', {})
        deliveries_wz_products = activity_data.get('deliveries_wz_products_summary', [])
        deliveries_centrala_products = activity_data.get('deliveries_centrala_products_summary', [])
        transfers_mm_products = activity_data.get('transfers_mm_products_summary', [])

        totals_str_parts = [f"<strong>{qty:,.2f} {unit}</strong>" for unit, qty in sorted(total_qty_by_unit.items())]
        totals_display = " | ".join(totals_str_parts) if totals_str_parts else "0 kg"

        def _render_doc_block(doc: Dict[str, Any]) -> str:
            category = doc.get('category', 'PRZESUNIECIE_MM')
            if category == 'DOSTAWA_ZEWNETRZNA':
                theme_grad = "linear-gradient(135deg, #1e3a8a, #2563eb)"
                badge_color = "#1e3a8a"
                doc_icon = "🚚"
                src_label = "Dostawca"
                dst_label = "Lokalizacja docelowa"
            elif category == 'DOSTAWA_CENTRALA':
                theme_grad = "linear-gradient(135deg, #3730a3, #4f46e5)"
                badge_color = "#3730a3"
                doc_icon = "🏢"
                src_label = "Dostawca / Magazyn"
                dst_label = "Lokalizacja docelowa"
            else:
                theme_grad = "linear-gradient(135deg, #065f46, #059669)"
                badge_color = "#065f46"
                doc_icon = "🔄"
                src_label = "Skąd (Magazyn)"
                dst_label = "Dokąd (Magazyn)"

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

            pdf_file_label = doc.get('pdf_filename') or ''

            return f"""
            <div style="margin-bottom: 24px; border: 1px solid #cbd5e1; border-radius: 12px; overflow: hidden; background: #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <div style="background: {theme_grad}; padding: 14px 18px; color: #ffffff; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.9;">{doc_icon} {doc.get('doc_title')}</div>
                        <div style="font-size: 18px; font-weight: 900; margin-top: 2px;">Dokument: {doc.get('order_ref')}</div>
                    </div>
                    {f'<div style="background: rgba(255,255,255,0.2); padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700;">📄 Załącznik: {pdf_file_label}</div>' if pdf_file_label else ''}
                </div>
                <div style="padding: 12px 18px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; font-size: 12px; line-height: 1.6;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="width: 50%; vertical-align: top;">
                                <div><span style="color: #64748b;">{src_label}:</span> <strong>{doc.get('source')}</strong></div>
                                <div><span style="color: #64748b;">{dst_label}:</span> <strong style="color: {badge_color};">{doc.get('destination')}</strong></div>
                            </td>
                            <td style="width: 50%; vertical-align: top;">
                                <div><span style="color: #64748b;">Wprowadził / Wydał:</span> <strong>{doc.get('created_by')}</strong> ({doc.get('created_str')})</div>
                                <div><span style="color: #64748b;">Przyjął / Zatwierdził:</span> <strong style="color: #166534;">{doc.get('accepted_by')}</strong> ({doc.get('accepted_str')})</div>
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

        wz_blocks = "".join(_render_doc_block(d) for d in deliveries_wz) if deliveries_wz else '<div style="padding: 14px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; font-size: 12px; margin-bottom: 18px;">Brak dostaw zewnętrznych (WZ) w tym dniu.</div>'
        centrala_blocks = "".join(_render_doc_block(d) for d in deliveries_centrala) if deliveries_centrala else '<div style="padding: 14px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; font-size: 12px; margin-bottom: 18px;">Brak dostaw z Centrali w tym dniu.</div>'
        mm_blocks = "".join(_render_doc_block(t) for t in transfers_mm) if transfers_mm else '<div style="padding: 14px; background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; font-size: 12px; margin-bottom: 18px;">Brak przesunięć międzymagazynowych MM w tym dniu.</div>'

        def _render_html_products_rows(prod_list: List[Dict[str, Any]], count_color: str) -> str:
            if not prod_list:
                return '<tr><td colspan="4" style="padding: 10px; text-align: center; color: #64748b;">Brak pozycji w tym zestawieniu.</td></tr>'
            rows = ""
            for idx, p in enumerate(prod_list, start=1):
                rows += f"""
                <tr style="border-bottom: 1px solid #e2e8f0; font-size: 12px;">
                    <td style="padding: 8px 12px; text-align: center; color: #64748b; font-weight: 600; width: 35px;">{idx}</td>
                    <td style="padding: 8px 12px; font-weight: 700; color: #0f172a;">{p.get('product_name')}</td>
                    <td style="padding: 8px 12px; text-align: center; font-weight: 800; color: {count_color}; width: 120px;">{p.get('count')} szt.</td>
                    <td style="padding: 8px 12px; text-align: right; font-weight: 800; color: #166534; width: 150px;">{p.get('total_qty'):,.2f} {p.get('unit')}</td>
                </tr>
                """
            return rows

        wz_products_rows = _render_html_products_rows(deliveries_wz_products, "#1e3a8a")
        centrala_products_rows = _render_html_products_rows(deliveries_centrala_products, "#3730a3")
        mm_products_rows = _render_html_products_rows(transfers_mm_products, "#065f46")

        # Lista załączonych dokumentów PDF
        pdf_attachments_list_html = ""
        summary_pdf_name = f"Raport_Zbiorczy_Dostaw_i_Przesuniec_{date_str}.pdf"
        pdf_attachments_list_html += f"""
        <div style="padding: 8px 12px; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 6px; font-size: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div><strong>📋 {summary_pdf_name}</strong></div>
            <div style="color: #2563eb; font-weight: 700;">Główny raport zbiorczy A4</div>
        </div>
        """
        for doc in all_documents:
            cat_icon = "🚚" if doc.get('category') == 'DOSTAWA_ZEWNETRZNA' else ("🏢" if doc.get('category') == 'DOSTAWA_CENTRALA' else "🔄")
            pdf_attachments_list_html += f"""
            <div style="padding: 8px 12px; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 6px; font-size: 12px; display: flex; justify-content: space-between; align-items: center;">
                <div><strong>{cat_icon} {doc.get('pdf_filename')}</strong> — {doc.get('doc_title')}: {doc.get('order_ref')}</div>
                <div style="color: #64748b; font-size: 11px;">{doc.get('source')} ➔ {doc.get('destination')} ({doc.get('items_count')} palet)</div>
            </div>
            """

        total_pdf_count = len(all_documents) + 1

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 860px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #cbd5e1;">
                
                <!-- Hero Header -->
                <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 28px 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 800; color: #38bdf8;">Magazyn • Dzienny Raport Operacyjny</div>
                    <div style="font-size: 24px; font-weight: 900; margin-top: 6px;">📋 Raport Zbiorczy Dostaw i Przesunięć</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Dzień: <strong>{date_str}</strong> | Wygenerowano: <strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}</strong></div>
                </div>

                <!-- KPI Banner (5 bloków) -->
                <div style="padding: 16px 20px; background: #f8fafc; border-bottom: 2px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; text-align: center;">
                        <tr>
                            <td style="width: 20%; padding: 8px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Dostawy WZ</div>
                                <div style="font-size: 20px; font-weight: 900; color: #1e3a8a; margin-top: 2px;">{len(deliveries_wz)}</div>
                            </td>
                            <td style="width: 20%; padding: 8px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Dostawa Centrala</div>
                                <div style="font-size: 20px; font-weight: 900; color: #3730a3; margin-top: 2px;">{len(deliveries_centrala)}</div>
                            </td>
                            <td style="width: 20%; padding: 8px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Przesunięcia MM</div>
                                <div style="font-size: 20px; font-weight: 900; color: #065f46; margin-top: 2px;">{len(transfers_mm)}</div>
                            </td>
                            <td style="width: 20%; padding: 8px; border-right: 1px solid #e2e8f0;">
                                <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Łącznie Palet</div>
                                <div style="font-size: 20px; font-weight: 900; color: #0284c7; margin-top: 2px;">{total_pallets}</div>
                            </td>
                            <td style="width: 20%; padding: 8px;">
                                <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Łączna Ilość</div>
                                <div style="font-size: 14px; font-weight: 900; color: #166534; margin-top: 4px;">{totals_display}</div>
                            </td>
                        </tr>
                    </table>
                </div>

                <div style="padding: 24px;">

                    <!-- SEKCJA 1: DOSTAWY ZEWNĘTRZNE (WZ) -->
                    <div style="margin-bottom: 28px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; border-bottom: 2px solid #1e3a8a; padding-bottom: 6px;">
                            <h2 style="font-size: 15px; font-weight: 900; color: #1e3a8a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                🚚 1. Dostawy Zewnętrzne (WZ) ({len(deliveries_wz)})
                            </h2>
                        </div>
                        {wz_blocks}
                    </div>

                    <!-- SEKCJA 2: DOSTAWA CENTRALA -->
                    <div style="margin-bottom: 28px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; border-bottom: 2px solid #3730a3; padding-bottom: 6px;">
                            <h2 style="font-size: 15px; font-weight: 900; color: #3730a3; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                🏢 2. Dostawa Centrala ({len(deliveries_centrala)})
                            </h2>
                        </div>
                        {centrala_blocks}
                    </div>

                    <!-- SEKCJA 3: PRZESUNIĘCIA MM (MIĘDZYMAGAZYNOWE) -->
                    <div style="margin-bottom: 28px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; border-bottom: 2px solid #065f46; padding-bottom: 6px;">
                            <h2 style="font-size: 15px; font-weight: 900; color: #065f46; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                🔄 3. Przesunięcia MM (Międzymagazynowe) ({len(transfers_mm)})
                            </h2>
                        </div>
                        {mm_blocks}
                    </div>

                    <!-- SEKCJA 4: PODSUMOWANIE ASORTYMENTU Z PODZIAŁEM NA 3 KATEGORIE -->
                    <div style="margin-bottom: 28px;">
                        <div style="margin-bottom: 14px; border-bottom: 2px solid #0f172a; padding-bottom: 6px;">
                            <h2 style="font-size: 15px; font-weight: 900; color: #0f172a; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">
                                📊 4. Zbiorcze Podsumowanie Asortymentu
                            </h2>
                        </div>

                        <!-- 4.1 Dostawy Zewnętrzne -->
                        <div style="margin-bottom: 18px;">
                            <div style="font-size: 12px; font-weight: 800; color: #1e3a8a; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                                🚚 4.1. Dostawy Zewnętrzne (WZ) ({len(deliveries_wz_products)})
                            </div>
                            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background: #eff6ff; color: #1e3a8a; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <th style="padding: 8px 12px; text-align: center; width: 35px;">Lp</th>
                                        <th style="padding: 8px 12px; text-align: left;">Produkt / Asortyment</th>
                                        <th style="padding: 8px 12px; text-align: center; width: 120px;">Liczba Palet</th>
                                        <th style="padding: 8px 12px; text-align: right; width: 150px;">Łączna Ilość</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {wz_products_rows}
                                </tbody>
                            </table>
                        </div>

                        <!-- 4.2 Dostawa Centrala -->
                        <div style="margin-bottom: 18px;">
                            <div style="font-size: 12px; font-weight: 800; color: #3730a3; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                                🏢 4.2. Dostawa Centrala ({len(deliveries_centrala_products)})
                            </div>
                            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background: #eef2ff; color: #3730a3; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <th style="padding: 8px 12px; text-align: center; width: 35px;">Lp</th>
                                        <th style="padding: 8px 12px; text-align: left;">Produkt / Asortyment</th>
                                        <th style="padding: 8px 12px; text-align: center; width: 120px;">Liczba Palet</th>
                                        <th style="padding: 8px 12px; text-align: right; width: 150px;">Łączna Ilość</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {centrala_products_rows}
                                </tbody>
                            </table>
                        </div>

                        <!-- 4.3 Przesunięcia MM -->
                        <div style="margin-bottom: 14px;">
                            <div style="font-size: 12px; font-weight: 800; color: #065f46; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                                🔄 4.3. Przesunięcia MM (Międzymagazynowe) ({len(transfers_mm_products)})
                            </div>
                            <table style="width: 100%; border-collapse: collapse; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden;">
                                <thead>
                                    <tr style="background: #f0fdf4; color: #065f46; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                        <th style="padding: 8px 12px; text-align: center; width: 35px;">Lp</th>
                                        <th style="padding: 8px 12px; text-align: left;">Produkt / Asortyment</th>
                                        <th style="padding: 8px 12px; text-align: center; width: 120px;">Liczba Palet</th>
                                        <th style="padding: 8px 12px; text-align: right; width: 150px;">Łączna Ilość</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {mm_products_rows}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- SEKCJA 5: ZAŁĄCZONE DOKUMENTY PDF DO DRUKU -->
                    <div style="margin-bottom: 10px; background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 10px; padding: 16px;">
                        <div style="font-size: 13px; font-weight: 900; color: #0f172a; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px;">
                            📎 5. Dołączone Raporty PDF do Druku ({total_pdf_count} dokumentów A4):
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-bottom: 10px;">
                            Do niniejszej wiadomości dołączono osobny oficjalny dokument PDF w układzie do druku A4 dla każdej zatwierdzonej operacji oraz zbiorczy raport dzienny:
                        </div>
                        {pdf_attachments_list_html}
                    </div>

                </div>

                <!-- Footer -->
                <div style="background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; text-align: center;">
                    Dzienny raport magazynowy wygenerowany automatycznie przez system RaportProdukcyjny. Wszystkie załączniki stanowią oficjalne dokumenty magazynowe do druku A4.
                </div>
            </div>
        </body>
        </html>
        """

    def generate_daily_summary_pdf(self, date_str: str, activity_data: Dict[str, Any]) -> Optional[str]:
        """Generuje plik PDF w układzie do druku A4 ze zbiorczym zestawieniem dostaw i przesunięć z podziałem na 3 grupy."""
        deliveries_wz = activity_data.get('deliveries_wz', [])
        deliveries_centrala = activity_data.get('deliveries_centrala', [])
        transfers_mm = activity_data.get('transfers_mm', [])

        total_pallets = activity_data.get('total_pallets', 0)
        total_qty_by_unit = activity_data.get('total_qty_by_unit', {})
        deliveries_wz_products = activity_data.get('deliveries_wz_products_summary', [])
        deliveries_centrala_products = activity_data.get('deliveries_centrala_products_summary', [])
        transfers_mm_products = activity_data.get('transfers_mm_products_summary', [])
        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        totals_str_parts = [f"{qty:,.2f} {unit}" for unit, qty in sorted(total_qty_by_unit.items())]
        totals_display = " | ".join(totals_str_parts) if totals_str_parts else "0 kg"

        def _render_pdf_doc_block(doc: Dict[str, Any]) -> str:
            category = doc.get('category', 'PRZESUNIECIE_MM')
            if category == 'DOSTAWA_ZEWNETRZNA':
                header_bg = "#eff6ff"
                header_color = "#1e3a8a"
                src_label = "Dostawca"
                dst_label = "Lokalizacja docelowa"
            elif category == 'DOSTAWA_CENTRALA':
                header_bg = "#eef2ff"
                header_color = "#3730a3"
                src_label = "Dostawca / Magazyn"
                dst_label = "Lokalizacja docelowa"
            else:
                header_bg = "#f0fdf4"
                header_color = "#065f46"
                src_label = "Skąd (Magazyn)"
                dst_label = "Dokąd (Magazyn)"

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
                    <div style="font-size: 12px; font-weight: 900;">{doc.get('doc_title')}: {doc.get('order_ref')}</div>
                    <div style="font-size: 9px; color: #475569;">
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

        wz_pdf_blocks = "".join(_render_pdf_doc_block(d) for d in deliveries_wz) if deliveries_wz else '<p style="color: #64748b; font-style: italic; margin-bottom: 10px; font-size: 9px;">Brak dostaw zewnętrznych (WZ) w tym dniu.</p>'
        centrala_pdf_blocks = "".join(_render_pdf_doc_block(d) for d in deliveries_centrala) if deliveries_centrala else '<p style="color: #64748b; font-style: italic; margin-bottom: 10px; font-size: 9px;">Brak dostaw z Centrali w tym dniu.</p>'
        mm_pdf_blocks = "".join(_render_pdf_doc_block(t) for t in transfers_mm) if transfers_mm else '<p style="color: #64748b; font-style: italic; margin-bottom: 10px; font-size: 9px;">Brak przesunięć międzymagazynowych MM w tym dniu.</p>'

        def _render_pdf_products_rows(prod_list: List[Dict[str, Any]], count_color: str) -> str:
            if not prod_list:
                return '<tr><td colspan="4" style="text-align: center; color: #64748b; font-style: italic; padding: 5px;">Brak pozycji w tym zestawieniu.</td></tr>'
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

        pdf_wz_products_rows = _render_pdf_products_rows(deliveries_wz_products, "#1e3a8a")
        pdf_centrala_products_rows = _render_pdf_products_rows(deliveries_centrala_products, "#3730a3")
        pdf_mm_products_rows = _render_pdf_products_rows(transfers_mm_products, "#065f46")

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
            padding: 9px 12px;
            margin-bottom: 10px;
            background: #f8fafc;
        }}
        .doc-title {{
            font-size: 15px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 0 3px 0;
            color: #0f172a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .doc-meta {{
            font-size: 9px;
            color: #475569;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 6px;
            margin-top: 6px;
            padding-top: 6px;
            border-top: 1px solid #cbd5e1;
            text-align: center;
        }}
        .kpi-item {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 5px;
        }}
        .kpi-label {{
            font-size: 7.5px;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
        }}
        .kpi-val {{
            font-size: 12px;
            font-weight: 900;
            color: #0f172a;
            margin-top: 2px;
        }}
        .section-title {{
            font-size: 11px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 12px 0 6px 0;
            padding-bottom: 3px;
            border-bottom: 1.5px solid #0f172a;
        }}
        .doc-card {{
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            margin-bottom: 8px;
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
            margin-top: 3px;
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
            margin-top: 12px;
            font-size: 8px;
            color: #64748b;
            text-align: center;
            border-top: 1px solid #e2e8f0;
            padding-top: 5px;
        }}
    </style>
</head>
<body>
    <div class="header-box">
        <div class="doc-title">
            <span>DZIENNY RAPORT ZBIORCZY: DOSTAWY I PRZESUNIĘCIA</span>
            <span style="font-size: 11px; color: #2563eb;">{date_str}</span>
        </div>
        <div class="doc-meta">
            Raport wygenerowano: <strong>{gen_now}</strong> | System RaportProdukcyjny (Moduł Magazynowy)
        </div>
        <div class="kpi-grid">
            <div class="kpi-item">
                <div class="kpi-label">Dostawy WZ</div>
                <div class="kpi-val" style="color: #1e3a8a;">{len(deliveries_wz)}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Dostawa Centrala</div>
                <div class="kpi-val" style="color: #3730a3;">{len(deliveries_centrala)}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Przesunięcia MM</div>
                <div class="kpi-val" style="color: #065f46;">{len(transfers_mm)}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Łącznie Palet</div>
                <div class="kpi-val" style="color: #0284c7;">{total_pallets}</div>
            </div>
            <div class="kpi-item">
                <div class="kpi-label">Łączna Ilość</div>
                <div class="kpi-val" style="color: #166534; font-size: 10px;">{totals_display}</div>
            </div>
        </div>
    </div>

    <div class="section-title" style="color: #1e3a8a; border-bottom-color: #1e3a8a;">
        1. DOSTAWY ZEWNĘTRZNE (WZ) [{len(deliveries_wz)}]
    </div>
    {wz_pdf_blocks}

    <div class="section-title" style="color: #3730a3; border-bottom-color: #3730a3;">
        2. DOSTAWA CENTRALA [{len(deliveries_centrala)}]
    </div>
    {centrala_pdf_blocks}

    <div class="section-title" style="color: #065f46; border-bottom-color: #065f46;">
        3. PRZESUNIĘCIA MM (MIĘDZYMAGAZYNOWE) [{len(transfers_mm)}]
    </div>
    {mm_pdf_blocks}

    <div class="section-title" style="color: #1e3a8a; border-bottom-color: #1e3a8a;">
        4.1. PODSUMOWANIE ASORTYMENTU: DOSTAWY ZEWNĘTRZNE (WZ) [{len(deliveries_wz_products)}]
    </div>
    <table class="report-table" style="margin-bottom: 10px; page-break-inside: avoid;">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt / Surowiec / Opakowanie</th>
                <th style="width: 90px; text-align: center;">Liczba Palet</th>
                <th style="width: 130px; text-align: right;">Łączna Ilość</th>
            </tr>
        </thead>
        <tbody>
            {pdf_wz_products_rows}
        </tbody>
    </table>

    <div class="section-title" style="color: #3730a3; border-bottom-color: #3730a3;">
        4.2. PODSUMOWANIE ASORTYMENTU: DOSTAWA CENTRALA [{len(deliveries_centrala_products)}]
    </div>
    <table class="report-table" style="margin-bottom: 10px; page-break-inside: avoid;">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt / Surowiec / Opakowanie</th>
                <th style="width: 90px; text-align: center;">Liczba Palet</th>
                <th style="width: 130px; text-align: right;">Łączna Ilość</th>
            </tr>
        </thead>
        <tbody>
            {pdf_centrala_products_rows}
        </tbody>
    </table>

    <div class="section-title" style="color: #065f46; border-bottom-color: #065f46;">
        4.3. PODSUMOWANIE ASORTYMENTU: PRZESUNIĘCIA MM [{len(transfers_mm_products)}]
    </div>
    <table class="report-table" style="margin-bottom: 10px; page-break-inside: avoid;">
        <thead>
            <tr>
                <th style="width: 25px; text-align: center;">Lp</th>
                <th style="text-align: left;">Produkt / Surowiec / Opakowanie</th>
                <th style="width: 90px; text-align: center;">Liczba Palet</th>
                <th style="width: 130px; text-align: right;">Łączna Ilość</th>
            </tr>
        </thead>
        <tbody>
            {pdf_mm_products_rows}
        </tbody>
    </table>

    <div class="footer-note">
        Dokument wygenerowany automatycznie z bazy danych systemu RaportProdukcyjny. Zawiera wyłącznie zatwierdzone przyjęcia zewnętrzne, centralne oraz międzymagazynowe z dnia {date_str}.
    </div>
</body>
</html>
        """
        return self._render_html_to_temp_pdf(html_content, prefix=f"raport_dzienny_{date_str}_")

    def send_daily_warehouse_summary_report(
        self,
        date_str: Optional[str] = None,
        force: bool = False,
        recipient_override: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Wysyła dzienny zbiorczy raport z dostaw i przesunięć z danego dnia na listę odbiorców.
        Dołącza zbiorczy raport PDF oraz OSOBNE DOKUMENTY PDF DO DRUKU A4 DLA KAŻDEJ ZAREJESTROWANEJ AKCJI.
        Jeśli w danym dniu nie było dostaw ani przesunięć i nie wymuszono wysyłki (force=False), raport nie jest wysyłany.
        Opcjonalny parametr recipient_override pozwala na wysyłkę testową wyłącznie na wskazane adresy e-mail.
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        dispatch_key = f"daily_summary_{date_str}_{'-'.join(recipient_override)}" if recipient_override else f"daily_summary_{date_str}"
        with self._dispatch_lock:
            if not force and not recipient_override and date_str in self._sent_daily_dates:
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

            recipients = [r.strip() for r in recipient_override if r and r.strip()] if recipient_override else config.recipients_list
            if not recipients:
                return False, "Brak zdefiniowanych adresów e-mail odbiorców w Ustawieniach E-mail."

            activity_data = self.get_daily_warehouse_activity(date_str)
            if not activity_data['has_activity'] and not force:
                return False, f"Brak zarejestrowanych dostaw i przesunięć w dniu {date_str} - raport nie został wysłany."

            subject_prefix = "[TEST] " if recipient_override else ""
            subject = f"{subject_prefix}📋 Raport Dzienny: Dostawy WZ ({activity_data['deliveries_wz_count']}), Centrala ({activity_data['deliveries_centrala_count']}), MM ({activity_data['transfers_mm_count']}) - {date_str} (Palety: {activity_data['total_pallets']})"
            body_html = self.build_daily_summary_report_html(date_str, activity_data)

            attachments: List[Tuple[str, str]] = []
            temp_files_to_cleanup: List[str] = []

            try:
                # 1. Zbiorczy raport dzienny PDF (A4)
                summary_pdf = self.generate_daily_summary_pdf(date_str, activity_data)
                if summary_pdf and os.path.exists(summary_pdf):
                    temp_files_to_cleanup.append(summary_pdf)
                    attachments.append((summary_pdf, f"Raport_Zbiorczy_Dostaw_i_Przesuniec_{date_str}.pdf"))

                # 2. Osobne raporty PDF (układ A4 do druku) dla każdej zatwierdzonej akcji
                for doc in activity_data.get('all_documents', []):
                    doc_pdf = None
                    if doc.get('raw_dostawa') is not None:
                        doc_pdf = self.generate_delivery_pdf(doc['raw_dostawa'], doc.get('raw_items', []))
                    elif doc.get('raw_transfer') is not None:
                        tr_dict = dict(doc['raw_transfer'])
                        tr_dict['items'] = doc.get('raw_items', [])
                        doc_pdf = self.generate_transfer_pdf(tr_dict)

                    if doc_pdf and os.path.exists(doc_pdf):
                        temp_files_to_cleanup.append(doc_pdf)
                        display_name = doc.get('pdf_filename') or os.path.basename(doc_pdf)
                        attachments.append((doc_pdf, display_name))

                ok, msg = self._send_raw_email(config, recipients, subject, body_html, attachments=attachments)
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

