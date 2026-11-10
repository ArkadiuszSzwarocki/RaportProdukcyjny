"""
Serwis do weryfikacji połączenia z serwerem SMTP oraz do wysyłania wiadomości e-mail (w tym raportów produkcyjnych z załącznikami).
"""
import os
import mimetypes
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import Header
from email.utils import formataddr
from email import encoders
from typing import List, Optional, Tuple, Dict, Any

from app.core.network_security import smtp_target_allowed, secure_smtp_connection
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository


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

            allowed, reason = smtp_target_allowed(smtp_server, smtp_port, smtp_security)
            if not allowed:
                return False, f"❌ {reason}"

            if smtp_security == 'SSL' or smtp_port == 465:
                server = secure_smtp_connection(smtp_server, smtp_port, 'SSL', timeout=12, context=ssl.create_default_context())
            else:
                server = secure_smtp_connection(smtp_server, smtp_port, smtp_security, timeout=12)

            server.login(smtp_username, smtp_password)
            server.quit()
            return True, "✅ Połączenie z serwerem SMTP oraz autoryzacja powiodły się!"
        except smtplib.SMTPAuthenticationError:
            return False, "❌ Błąd autoryzacji SMTP: Nieprawidłowy login lub hasło skrzynki e-mail."
        except smtplib.SMTPConnectError:
            return False, "❌ Nie można połączyć się ze skonfigurowanym serwerem SMTP."
        except ssl.SSLCertVerificationError as error:
            if error.verify_code == 62:
                return False, "❌ Certyfikat TLS nie pasuje do adresu serwera SMTP. Wpisz nazwę serwera pocztowego podaną przez dostawcę skrzynki, zgodną z jego certyfikatem. Login i hasło nie zostały jeszcze sprawdzone."
            return False, "❌ Nie można zweryfikować certyfikatu TLS serwera SMTP. Sprawdź jego ważność i konfigurację u dostawcy poczty."
        except Exception:
            return False, "❌ Nie udało się bezpiecznie przetestować połączenia SMTP."
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

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
                    'configured': bool(user_config.smtp_server and user_config.smtp_username and user_config.smtp_password)
                }

        sys_config = self.settings_repo.get_system_config()
        configured = bool(
            sys_config.smtp_server
            and sys_config.smtp_username
            and sys_config.smtp_password
        )
        return {
            'server': sys_config.smtp_server,
            'port': sys_config.smtp_port,
            'security': sys_config.smtp_security,
            'username': sys_config.smtp_username,
            'password': sys_config.smtp_password,
            'sender_name': sys_config.sender_name or 'Raport Produkcyjny',
            'is_custom': False,
            'configured': configured
        }

    def send_report_email(
        self,
        to_emails: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[str]] = None,
        user_id: Optional[int] = None,
        cc_emails: Optional[List[str]] = None,
        log_connection=None,
        log_source: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Wysyła wiadomość e-mail z raportem i załącznikami."""
        config = {}
        to_emails = list(dict.fromkeys(to_emails or []))
        to_keys = {address.lower() for address in to_emails}
        cc_emails = list(dict.fromkeys(address for address in (cc_emails or []) if address.lower() not in to_keys))
        envelope_recipients = to_emails + cc_emails

        def record(success, error=None):
            try:
                from app.services.email_log_service import EmailLogService
                EmailLogService.log_email_attempt(
                    sender=config.get('username') or 'Konto systemowe',
                    recipients=envelope_recipients, subject=subject,
                    source=log_source or ('Auto-Raport' if 'Auto' in subject else ('Raport Zmianowy' if 'Raport' in subject else 'Inne')),
                    linia='AGRO' if 'AGRO' in subject else ('PSD' if 'PSD' in subject else None),
                    success=success, error_message=error, attachments=attachments,
                    connection=log_connection,
                )
                return True
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Could not persist email attempt history')
                return False

        if not to_emails:
            message = 'Brak podanych adresów e-mail odbiorców.'
            record(False, message)
            return False, message
        config = self.get_smtp_config_for_user(user_id) or {}
        if not config or not config.get('configured'):
            message = 'Brak skonfigurowanego konta SMTP nadawcy.'
            record(False, message)
            return False, message
        allowed, reason = smtp_target_allowed(config.get('server'), config.get('port'), config.get('security'))
        if not allowed:
            message = f'Wysyłka zablokowana przez politykę bezpieczeństwa SMTP: {reason}'
            record(False, message)
            return False, message

        server = None
        try:
            msg = MIMEMultipart()
            if config.get('sender_name'):
                msg['From'] = formataddr((str(Header(config['sender_name'], 'utf-8')), config['username']))
            else:
                msg['From'] = config['username']
            msg['To'] = ", ".join(to_emails)
            if cc_emails:
                msg['Cc'] = ", ".join(cc_emails)
            msg['Subject'] = Header(subject, 'utf-8')
            msg.attach(MIMEText(body_html, 'html', 'utf-8'))

            if attachments:
                for file_path in attachments:
                    if os.path.isfile(file_path):
                        filename = os.path.basename(file_path)
                        with open(file_path, 'rb') as file_handle:
                            content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                            part = MIMEBase(*content_type.split('/', 1))
                            part.set_payload(file_handle.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                        msg.attach(part)
                    else:
                        message = "Brak wybranego załącznika raportu. Wygeneruj raport ponownie."
                        record(False, message)
                        return False, message

            if config['security'] == 'SSL' or config['port'] == 465:
                server = secure_smtp_connection(config['server'], config['port'], 'SSL', timeout=15, context=ssl.create_default_context())
            else:
                server = secure_smtp_connection(config['server'], config['port'], config['security'], timeout=15)

            server.login(config['username'], config['password'])
            refused = server.sendmail(config['username'], envelope_recipients, msg.as_string())
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            # QUIT failure after SMTP acceptance must not trigger a duplicate resend.

            sender_info = f"konto własne ({config.get('username')})" if config.get('is_custom') else f"konto systemowe ({config.get('username')})"
            msg_res = f"✅ E-mail wysłany pomyślnie do {len(envelope_recipients)} odbiorcy/odbiorców ({sender_info})."

            if not record(True):
                msg_res += ' Uwaga: nie udało się zapisać historii wysyłki.'
            return True, msg_res
        except Exception as exc:
            if isinstance(exc, smtplib.SMTPRecipientsRefused):
                message = 'Serwer odrzucił co najmniej jednego odbiorcę. Część odbiorców mogła otrzymać wiadomość; sprawdź adresy przed ponowieniem.'
            elif isinstance(exc, smtplib.SMTPAuthenticationError):
                message = 'Serwer SMTP odrzucił login lub hasło nadawcy.'
            elif isinstance(exc, ssl.SSLCertVerificationError):
                message = 'Nieprawidłowy certyfikat TLS serwera SMTP.'
            elif isinstance(exc, TimeoutError):
                message = 'Przekroczono czas oczekiwania na serwer SMTP.'
            else:
                message = 'Nie udało się wysłać wiadomości przez skonfigurowany serwer SMTP.'
            record(False, message)
            return False, message
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
