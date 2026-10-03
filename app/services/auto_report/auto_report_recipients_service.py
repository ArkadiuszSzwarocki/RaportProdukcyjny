"""Resolve automatic report recipients without borrowing private user settings."""
import os
import logging
from typing import List
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

logger = logging.getLogger(__name__)


class AutoReportRecipientsService:
    @staticmethod
    def get_default_recipients(linia: str = 'AGRO') -> List[str]:
        """The central recipient dictionary is authoritative, including all-disabled."""
        try:
            recipients = UserEmailSettingsRepository().get_all_recipients(only_active=False, strict=True)
        except Exception:
            logger.exception('Cannot verify automatic report recipients for %s', linia)
            return []
        if recipients:
            emails = []
            seen = set()
            for recipient in recipients:
                email = str(recipient.get('email') or '').strip()
                if recipient.get('aktywny') in (1, True) and email and email.lower() not in seen:
                    seen.add(email.lower())
                    emails.append(email)
            return emails
        # Only an explicitly configured system fallback, never a random user's
        # private defaults or the unrelated OSIP warehouse mailing list.
        raw = os.getenv('DEFAULT_REPORT_RECIPIENTS', '')
        emails = []
        seen = set()
        for value in raw.replace(';', ',').split(','):
            email = value.strip()
            if email and email.lower() not in seen:
                seen.add(email.lower())
                emails.append(email)
        return emails
