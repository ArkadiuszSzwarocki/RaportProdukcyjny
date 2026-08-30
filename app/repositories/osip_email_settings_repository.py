"""
Repozytorium zarządzające dedykowaną konfiguracją konta pocztowego oraz odbiorców dla modułu OSIP.
"""
from typing import Optional, Union
from app.core.database import get_db_connection
from app.models.osip_email_settings_model import OsipEmailSettingsModel


class OsipEmailSettingsRepository:
    """Obsługa CRUD na tabeli osip_email_settings."""

    @staticmethod
    def _ensure_table(conn) -> None:
        """Upewnia się, że tabela osip_email_settings istnieje w bazie danych."""
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS osip_email_settings (
                    id INT PRIMARY KEY,
                    smtp_server VARCHAR(150) NOT NULL DEFAULT 'smtp.gmail.com',
                    smtp_port INT NOT NULL DEFAULT 465,
                    smtp_security VARCHAR(10) NOT NULL DEFAULT 'SSL',
                    smtp_username VARCHAR(150) NOT NULL DEFAULT '',
                    smtp_password VARCHAR(255) NOT NULL DEFAULT '',
                    sender_name VARCHAR(150) DEFAULT 'Magazyn Centralny -> OSIP',
                    odbiorcy TEXT,
                    auto_send_on_dispatch TINYINT(1) DEFAULT 1,
                    is_active TINYINT(1) DEFAULT 1,
                    updated_by VARCHAR(100) DEFAULT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute("""
                INSERT IGNORE INTO osip_email_settings 
                (id, smtp_server, smtp_port, smtp_security, smtp_username, smtp_password, sender_name, odbiorcy, auto_send_on_dispatch, is_active, updated_by)
                VALUES (1, 'smtp.gmail.com', 465, 'SSL', '', '', 'Magazyn Centralny -> OSIP', '', 1, 1, 'System');
            """)
            conn.commit()
            cursor.close()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass

    def get_settings(self) -> OsipEmailSettingsModel:
        """Pobiera aktualną konfigurację e-mail dla OSIP."""
        conn = get_db_connection()
        try:
            self._ensure_table(conn)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM osip_email_settings WHERE id = 1 LIMIT 1")
            row = cursor.fetchone()
            cursor.close()

            if row:
                return OsipEmailSettingsModel(
                    id=row['id'],
                    smtp_server=row.get('smtp_server') or 'smtp.gmail.com',
                    smtp_port=int(row.get('smtp_port') or 465),
                    smtp_security=row.get('smtp_security') or 'SSL',
                    smtp_username=row.get('smtp_username') or '',
                    smtp_password=row.get('smtp_password') or '',
                    sender_name=row.get('sender_name') or 'Magazyn Centralny -> OSIP',
                    odbiorcy=row.get('odbiorcy') or '',
                    auto_send_on_dispatch=bool(row.get('auto_send_on_dispatch', 1)),
                    is_active=bool(row.get('is_active', 1)),
                    updated_by=row.get('updated_by'),
                    updated_at=row.get('updated_at')
                )
            return OsipEmailSettingsModel()
        finally:
            conn.close()

    def save_settings(
        self,
        model_or_server: Optional[Union[OsipEmailSettingsModel, str]] = None,
        smtp_port: int = 465,
        smtp_security: str = "SSL",
        smtp_username: str = "",
        smtp_password: str = "",
        sender_name: str = "Magazyn Centralny -> OSIP",
        odbiorcy: str = "",
        auto_send_on_dispatch: bool = True,
        is_active: bool = True,
        updated_by: Optional[str] = None,
        *,
        smtp_server: Optional[str] = None,
        **kwargs
    ) -> OsipEmailSettingsModel:
        """Zapisuje lub aktualizuje konfigurację konta nadawcy i odbiorców dla OSIP."""
        if isinstance(model_or_server, OsipEmailSettingsModel):
            _server = model_or_server.smtp_server or ""
            _port = model_or_server.smtp_port or 465
            _security = model_or_server.smtp_security or "SSL"
            _username = model_or_server.smtp_username or ""
            _password = model_or_server.smtp_password or ""
            _sender_name = model_or_server.sender_name or "Magazyn Centralny -> OSIP"
            _odbiorcy = model_or_server.odbiorcy or ""
            _auto_send = model_or_server.auto_send_on_dispatch
            _active = model_or_server.is_active
            _updated_by = model_or_server.updated_by or updated_by
        else:
            _server = smtp_server if smtp_server is not None else (str(model_or_server) if model_or_server is not None else "")
            _port = smtp_port
            _security = smtp_security
            _username = smtp_username
            _password = smtp_password
            _sender_name = sender_name
            _odbiorcy = odbiorcy
            _auto_send = auto_send_on_dispatch
            _active = is_active
            _updated_by = updated_by

        conn = get_db_connection()
        try:
            self._ensure_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO osip_email_settings 
                (id, smtp_server, smtp_port, smtp_security, smtp_username, smtp_password, sender_name, odbiorcy, auto_send_on_dispatch, is_active, updated_by, updated_at)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    smtp_server = VALUES(smtp_server),
                    smtp_port = VALUES(smtp_port),
                    smtp_security = VALUES(smtp_security),
                    smtp_username = VALUES(smtp_username),
                    smtp_password = IF(VALUES(smtp_password) != '' AND VALUES(smtp_password) IS NOT NULL, VALUES(smtp_password), smtp_password),
                    sender_name = VALUES(sender_name),
                    odbiorcy = VALUES(odbiorcy),
                    auto_send_on_dispatch = VALUES(auto_send_on_dispatch),
                    is_active = VALUES(is_active),
                    updated_by = VALUES(updated_by),
                    updated_at = NOW()
                """,
                (
                    _server.strip(),
                    int(_port),
                    _security.strip().upper(),
                    _username.strip(),
                    _password.strip(),
                    _sender_name.strip() or 'Magazyn Centralny -> OSIP',
                    _odbiorcy.strip(),
                    1 if _auto_send else 0,
                    1 if _active else 0,
                    _updated_by
                )
            )
            conn.commit()
            cursor.close()
            return self.get_settings()
        finally:
            conn.close()

