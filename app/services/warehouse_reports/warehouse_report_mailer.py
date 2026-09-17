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
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{config.sender_name or 'System Magazynowy'} <{config.smtp_user}>"
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject

            html_part = MIMEText(body_html, 'html', 'utf-8')
            msg.attach(html_part)

            if attachments:
                for att in attachments:
                    if not att:
                        continue
                    file_path, display_name = att
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
            if config.smtp_use_ssl:
                server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=25)
            else:
                server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=25)
                if config.smtp_use_tls:
                    server.starttls()

            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)

            server.sendmail(config.smtp_user, recipients, msg.as_string())
            server.quit()
            return True, "Wiadomość e-mail wysłana pomyślnie."

        except Exception as ex:
            return False, f"Błąd wysyłki SMTP: {str(ex)}"
