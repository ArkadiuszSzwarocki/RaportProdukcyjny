"""
Model danych konfiguracji dedykowanego konta pocztowego oraz odbiorców dla raportów OSIP.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class OsipEmailSettingsModel:
    id: int = 1
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_security: str = "SSL"
    smtp_username: str = ""
    smtp_password: str = ""
    sender_name: str = "Magazyn Centralny -> OSIP"
    odbiorcy: str = ""
    auto_send_on_dispatch: bool = False
    daily_report_enabled: bool = True
    daily_report_time: str = "15:00"
    last_daily_report_date: Optional[str] = None
    is_active: bool = True
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None

    @property
    def recipient_emails(self) -> str:
        return self.odbiorcy or ""

    @property
    def recipients_list(self) -> List[str]:
        """Zwraca sparsowaną listę unikalnych adresów e-mail odbiorców."""
        if not self.odbiorcy:
            return []
        raw = self.odbiorcy.replace(';', ',').replace('\n', ',').replace('\r', '')
        emails = [e.strip() for e in raw.split(',') if e.strip()]
        seen = set()
        res = []
        for e in emails:
            e_lower = e.lower()
            if e_lower not in seen:
                seen.add(e_lower)
                res.append(e)
        return res

    @property
    def is_configured(self) -> bool:
        """Zwraca True, jeśli podano serwer, login i hasło konta nadawcy."""
        return bool(
            self.smtp_server
            and self.smtp_username
            and self.smtp_password
            and self.is_active
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konwertuje model do słownika JSON-serializable."""
        return {
            "id": self.id,
            "smtp_server": self.smtp_server,
            "smtp_port": self.smtp_port,
            "smtp_security": self.smtp_security,
            "smtp_username": self.smtp_username,
            "sender_name": self.sender_name,
            "odbiorcy": self.odbiorcy,
            "auto_send_on_dispatch": self.auto_send_on_dispatch,
            "daily_report_enabled": self.daily_report_enabled,
            "daily_report_time": self.daily_report_time,
            "last_daily_report_date": self.last_daily_report_date,
            "is_active": self.is_active,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(self.updated_at, datetime) else self.updated_at,
            "is_configured": self.is_configured
        }
