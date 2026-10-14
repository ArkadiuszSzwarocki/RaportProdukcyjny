"""
Resolves the SMTP sender used by warehouse reports: always the global system mailbox.
"""
from dataclasses import replace
from typing import Any, Optional

from app.models.osip_email_settings_model import OsipEmailSettingsModel
from app.repositories.user_email_settings_repository import UserEmailSettingsRepository


class WarehouseSystemSenderResolver:
    """Overlays system account SMTP credentials onto the warehouse report settings.

    Recipients, activation flag and schedule stay in the warehouse settings; only the
    sending mailbox (server, port, security, login, password, sender name) comes from the system account.
    """

    def __init__(self, system_settings_repo: Optional[Any] = None):
        self._system_settings_repo = system_settings_repo or UserEmailSettingsRepository()

    def resolve(self, warehouse_config: OsipEmailSettingsModel) -> OsipEmailSettingsModel:
        system_config = self._system_settings_repo.get_system_config()
        return replace(
            warehouse_config,
            smtp_server=system_config.smtp_server,
            smtp_port=system_config.smtp_port,
            smtp_security=system_config.smtp_security,
            smtp_username=system_config.smtp_username,
            smtp_password=system_config.smtp_password,
            sender_name=system_config.sender_name or warehouse_config.sender_name,
        )
