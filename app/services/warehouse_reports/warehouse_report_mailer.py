"""
Moduł odpowiedzialny za bezpieczną wysyłkę e-mail SMTP z załącznikami PDF.
"""
from typing import Tuple, List, Optional
import os
import smtplib
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

        try:
            smtp_server = getattr(config, 'smtp_server', None) or getattr(config, 'smtp_host', '')
            smtp_user = getattr(config, 'smtp_username', None) or getattr(config, 'smtp_user', '')
            smtp_password = getattr(config, 'smtp_password', '')
            smtp_port = int(getattr(config, 'smtp_port', 465))
            smtp_security = getattr(config, 'smtp_security', 'SSL')
            use_ssl = (smtp_security == 'SSL') or getattr(config, 'smtp_use_ssl', False)
            use_tls = (smtp_security == 'TLS') or getattr(config, 'smtp_use_tls', False)

            msg = MIMEMultipart('mixed')
            msg['From'] = f"{config.sender_name or 'System Magazynowy'} <{smtp_user}>"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject

            html_part = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(html_part)

            if attachments:
                for att in attachments:
                    if not att:
                        continue
                    if isinstance(att, tuple):
                        file_path, display_name = att
                    else:
                        file_path = att
                        display_name = os.path.basename(att)

                    if not file_path or not os.path.exists(file_path):
                        continue

                    try:
                        with open(file_path, 'rb') as f:
                            part = MIMEApplication(f.read(), Name=display_name)
                        part['Content-Disposition'] = f'attachment; filename="{display_name}"'
                        msg.attach(part)
                    except Exception as e:
                        print(f"[MAILER] Ostrzeżenie przy dołączaniu {display_name}: {e}")

            server = None
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
                if use_tls:
                    server.starttls()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.sendmail(smtp_user, recipients, msg.as_string())
            server.quit()
            return True, "Wiadomość e-mail wysłana pomyślnie."

        except Exception as ex:
            return False, f"Błąd wysyłki SMTP: {str(ex)}"

