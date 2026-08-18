"""
Model reprezentujący indywidualne ustawienia SMTP użytkownika.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserEmailSettingsModel:
    id: Optional[int] = None
    user_id: int = 0
    smtp_server: str = "smtp.wp.pl"
    smtp_port: int = 465
    smtp_security: str = "SSL"  # SSL, TLS, NONE
    smtp_username: str = ""
    smtp_password: str = ""
    sender_name: Optional[str] = None
    domyslni_odbiorcy: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
