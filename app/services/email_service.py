"""
Serwis do weryfikacji połączenia z serwerem SMTP oraz do wysyłania wiadomości e-mail (w tym raportów produkcyjnych z załącznikami).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from email.utils import formataddr
from email import encoders
from typing import List, Optional, Tuple, Dict, Any

from app.repositories.user_email_settings_repository import UserEmailSettingsRepository
from app.models.user_email_settings_model import UserEmailSettingsModel

class EmailService:
    """Usługa wysyłania wiadomości e-mail oraz testowania połączenia SMTP w oparciu o konta użytkowników."""

    def __init__(self):
        self.settings_repo = UserEmailSettingsRepository()

    def test_connection(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: str,
        smtp_password: str
    ) -> Tuple[bool, str]:
        """Testuje bezpośrednio podłączenie i autoryzację na serwerze SMTP."""
        server = None
        try:
            smtp_server = (smtp_server or '').strip()
            smtp_port = int(smtp_port) if smtp_port else 465
            smtp_security = (smtp_security or 'SSL').strip().upper()
            smtp_username = (smtp_username or '').strip()
            smtp_password = (smtp_password or '').strip()

            if not smtp_server or not smtp_username or not smtp_password:
                return False, "❌ Podaj serwer SMTP, login oraz hasło konta."

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
            return True, "✅ Połączenie z serwerem SMTP oraz autoryzacja powiodły się!"
        except smtplib.SMTPAuthenticationError:
            return False, "❌ Błąd autoryzacji SMTP: Nieprawidłowy login lub hasło skrzynki e-mail."
        except smtplib.SMTPConnectError:
            return False, f"❌ Błąd połączenia: Nie można połączyć się z serwerem {smtp_server}:{smtp_port}."
        except Exception as e:
            return False, f"❌ Błąd połączenia z serwerem SMTP: {str(e)}"

    def test_smtp_connection(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: str,
        smtp_password: str
    ) -> Tuple[bool, str]:
        """Alias dla zgodności z API."""
        return self.test_connection(smtp_server, smtp_port, smtp_security, smtp_username, smtp_password)

    def get_smtp_config_for_user(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Zwraca konfigurację konta SMTP:
        1. Indywidualną dla użytkownika (jeśli podano user_id i ma skonfigurowaną skrzynkę).
        2. Główną konfigurację konta systemowego/firmowego (z możliwością modyfikacji w bazie).
        """
        if user_id and int(user_id) > 0:
            user_config = self.settings_repo.get_by_user_id(int(user_id))
            if user_config and user_config.is_active and user_config.smtp_username and user_config.smtp_password:
                return {
                    'server': user_config.smtp_server,
                    'port': user_config.smtp_port,
                    'security': user_config.smtp_security,
                    'username': user_config.smtp_username,
                    'password': user_config.smtp_password,
                    'sender_name': user_config.sender_name or user_config.smtp_username,
                    'is_custom': True,
                    'configured': True
                }

        # Pobierz Główne Konto Systemowe / Firmowe (zarządzane z bazy)
        sys_config = self.settings_repo.get_system_config()
        return {
            'server': sys_config.smtp_server,
            'port': sys_config.smtp_port,
            'security': sys_config.smtp_security,
            'username': sys_config.smtp_username,
            'password': sys_config.smtp_password,
            'sender_name': sys_config.sender_name or 'Raport Produkcyjny AGRO',
            'is_custom': False,
            'configured': True
        }

    def send_report_email(
        self,
        to_emails: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[str]] = None,
        user_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Wysyła wiadomość e-mail z raportem i załącznikami."""
        if not to_emails:
            return False, "Brak podanych adresów e-mail odbiorców."

        config = self.get_smtp_config_for_user(user_id)
        if not config or not config.get('username') or not config.get('password'):
            return False, "❌ Brak skonfigurowanego konta e-mail użytkownika. Skonfiguruj własną skrzynkę SMTP w panelu Ustawienia E-mail."

        server = None
        try:
            # Tworzenie wiadomości MIME
            msg = MIMEMultipart()
            if config.get('sender_name'):
                msg['From'] = formataddr((str(Header(config['sender_name'], 'utf-8')), config['username']))
            else:
                msg['From'] = config['username']
            msg['To'] = ", ".join(to_emails)
            msg['Subject'] = Header(subject, 'utf-8')

            # Dodanie treści HTML
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            # Dodanie załączników
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                        msg.attach(part)

            # Nawiązanie połączenia SMTP
            if config['security'] == 'SSL' or config['port'] == 465:
                server = smtplib.SMTP_SSL(config['server'], config['port'], timeout=15)
            else:
                server = smtplib.SMTP(config['server'], config['port'], timeout=15)
                server.ehlo()
                if config['security'] == 'TLS' or config['port'] == 587:
                    server.starttls()
                    server.ehlo()

            server.login(config['username'], config['password'])
            server.sendmail(config['username'], to_emails, msg.as_string())
            server.quit()

            sender_info = f"konto własne ({config.get('username')})" if config.get('is_custom') else f"konto systemowe ({config.get('username')})"
            msg_res = f"✅ E-mail wysłany pomyślnie do {len(to_emails)} odbiorcy/odbiorców ({sender_info})."

            try:
                from app.services.email_log_service import EmailLogService
                source_label = 'Auto-Raport' if 'Auto' in subject else ('Raport Zmianowy' if 'Raport' in subject else 'Inne')
                linia_val = 'AGRO' if 'AGRO' in subject else ('PSD' if 'PSD' in subject else None)
                EmailLogService.log_email_attempt(
                    sender=sender_str,
                    recipients=to_emails,
                    subject=subject,
                    source=source_label,
                    linia=linia_val,
                    success=True,
                    error_message=None,
                    attachments=attachments
                )
            except Exception:
                pass

            return True, msg_res
        except Exception as e:
            err_msg = f"❌ Błąd wysyłania e-maila: {str(e)}"
            try:
                from app.services.email_log_service import EmailLogService
                source_label = 'Auto-Raport' if 'Auto' in subject else ('Raport Zmianowy' if 'Raport' in subject else 'Inne')
                linia_val = 'AGRO' if 'AGRO' in subject else ('PSD' if 'PSD' in subject else None)
                EmailLogService.log_email_attempt(
                    sender=config.get('username', 'system') if config else 'system',
                    recipients=to_emails,
                    subject=subject,
                    source=source_label,
                    linia=linia_val,
                    success=False,
                    error_message=str(e),
                    attachments=attachments
                )
            except Exception:
                pass

            return False, err_msg
