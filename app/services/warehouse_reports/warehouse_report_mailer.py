"""
Moduł odpowiedzialny za bezpieczną wysyłkę e-mail SMTP z załącznikami PDF.
"""
from typing import Tuple, List, Optional
import os
import smtplib
import ssl
from app.core.network_security import smtp_target_allowed
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from app.models.osip_email_settings_model import OsipEmailSettingsModel


class WarehouseReportMailer:
    @staticmethod
    def send_raw_email(
        config: OsipEmailSettingsModel,
        recipients: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[Tuple[str, str]]] = None
    ) -> Tuple[bool, str]:
        """Wysyła wiadomość e-mail przez serwer SMTP zdefiniowany w config z obsługą wielu załączników."""
        if not recipients:
            return False, "Brak adresatów wiadomości e-mail."

        server = None
        try:
            smtp_server = getattr(config, 'smtp_server', None) or getattr(config, 'smtp_host', '')
            smtp_user = getattr(config, 'smtp_username', None) or getattr(config, 'smtp_user', '')
            smtp_password = getattr(config, 'smtp_password', '')
            smtp_port = int(getattr(config, 'smtp_port', 465))
            smtp_security = str(getattr(config, 'smtp_security', 'SSL') or 'SSL').strip().upper()
            use_ssl = (smtp_security == 'SSL') or getattr(config, 'smtp_use_ssl', False)
            use_tls = (smtp_security == 'TLS') or getattr(config, 'smtp_use_tls', False)
            allowed, reason = smtp_target_allowed(smtp_server, smtp_port, 'SSL' if use_ssl else 'TLS' if use_tls else 'NONE')
            if not allowed:
                return False, reason

            msg = MIMEMultipart('mixed')
            msg['From'] = f"{config.sender_name or 'System Magazynowy'} <{smtp_user}>"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject

            html_part = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(html_part)

            if attachments:
                for att in attachments:
                    if not att:
                        return False, "Brak wybranego załącznika raportu."
                    if isinstance(att, tuple):
                        file_path, display_name = att
                    else:
                        file_path = att
                        display_name = os.path.basename(att)

                    if not file_path or not os.path.isfile(file_path):
                        return False, "Brak wybranego załącznika raportu. Wygeneruj raport ponownie."

                    try:
                        with open(file_path, 'rb') as f:
                            part = MIMEApplication(f.read(), Name=display_name)
                        part['Content-Disposition'] = f'attachment; filename="{display_name}"'
                        msg.attach(part)
                    except OSError:
                        return False, "Nie można odczytać załącznika raportu."

            server = None
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
                if use_tls:
                    server.starttls(context=ssl.create_default_context())

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            refused = server.sendmail(smtp_user, recipients, msg.as_string())
            if refused:
                return False, "Serwer odrzucił część odbiorców. Pozostali mogli otrzymać raport; sprawdź adresy przed ponowieniem wysyłki."
            return True, "Wiadomość e-mail wysłana pomyślnie."

        except Exception:
            return False, "Nie udało się wysłać wiadomości przez skonfigurowany serwer SMTP."
        finally:
            WarehouseReportMailer._close(server)

    @staticmethod
    def test_smtp_connection(
        smtp_server: str,
        smtp_port: int = 465,
        smtp_security: str = "SSL",
        smtp_username: str = "",
        smtp_password: str = ""
    ) -> Tuple[bool, str]:
        """Testuje połączenie SMTP."""
        server = None
        try:
            smtp_security = str(smtp_security or 'SSL').strip().upper()
            smtp_port = int(smtp_port)
            allowed, reason = smtp_target_allowed(smtp_server, smtp_port, smtp_security)
            if not allowed:
                return False, reason
            use_ssl = (smtp_security == 'SSL')
            use_tls = (smtp_security == 'TLS')
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            return True, "Połączenie z serwerem SMTP powiodło się."
        except Exception:
            return False, "Nie udało się bezpiecznie przetestować połączenia SMTP."
        finally:
            WarehouseReportMailer._close(server)

    @staticmethod
    def _close(server):
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass

