"""
Moduł odpowiedzialny za ustalanie listy odbiorców e-mail dla automatycznych raportów.
"""
import os
import logging
from typing import List
from app.core.database import get_db_connection
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

logger = logging.getLogger(__name__)


class AutoReportRecipientsService:
    @staticmethod
    def get_default_recipients(linia: str = 'AGRO') -> List[str]:
        """Pobiera domyślną listę odbiorców e-mail dla raportu."""
        emails = []
        try:
            repo = UserEmailSettingsRepository()
            recipients = repo.get_all_recipients(only_active=True)
            for r in recipients:
                em = (r.get('email') or '').strip()
                if em and em.lower() not in [x.lower() for x in emails]:
                    emails.append(em)
            if emails:
                return emails
        except Exception as e:
            logger.warning("[AUTO_REPORT_RECIPIENTS] Nie udało się pobrać odbiorców ze słownika: %s", e)

        # Fallback z bazy z konfiguracji użytkowników
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT domyslni_odbiorcy FROM uzytkownik_email_settings WHERE domyslni_odbiorcy IS NOT NULL AND domyslni_odbiorcy != '' LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row and row.get('domyslni_odbiorcy'):
                raw = row['domyslni_odbiorcy']
                parsed = [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]
                try:
                    all_dict = UserEmailSettingsRepository().get_all_recipients(only_active=False)
                    inactive_emails = [r['email'].strip().lower() for r in all_dict if not (r.get('aktywny') == 1 or r.get('aktywny') is True)]
                    if inactive_emails:
                        parsed = [e for e in parsed if e.lower() not in inactive_emails]
                except Exception:
                    pass
                if parsed:
                    return parsed
        except Exception:
            pass

        env_recipients = os.getenv('DEFAULT_REPORT_RECIPIENTS', '')
        if env_recipients:
            return [e.strip() for e in env_recipients.replace(';', ',').split(',') if e.strip()]

        try:
            from app.repositories.osip_email_settings_repository import OsipEmailSettingsRepository
            wh_settings = OsipEmailSettingsRepository().get_settings()
            if wh_settings and wh_settings.recipients_list:
                return wh_settings.recipients_list
        except Exception:
            pass

        return []
