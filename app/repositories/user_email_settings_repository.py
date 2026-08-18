"""
Repozytorium do zarządzania indywidualnymi ustawieniami SMTP użytkowników (Liderów) w bazie danych.
"""
from typing import Optional, Dict, Any
from app.db import get_db_connection
from app.models.user_email_settings_model import UserEmailSettingsModel


class UserEmailSettingsRepository:
    """Obsługa operacji CRUD na tabeli uzytkownik_email_settings dla kont użytkowników oraz konta systemowego (user_id=0)."""

    DEFAULT_SYSTEM_CONFIG = {
        'smtp_server': 'smtp.wp.pl',
        'smtp_port': 465,
        'smtp_security': 'SSL',
        'smtp_username': 'Arkadiusz.szwarocki@wp.pl',
        'smtp_password': 'FILIPINKA2025',
        'sender_name': 'Raport Produkcyjny AGRO'
    }

    def get_system_config(self) -> UserEmailSettingsModel:
        """Pobiera globalną konfigurację konta systemowego (user_id=0). Jeśli brak w bazie, zwraca domyślną."""
        cfg = self.get_by_user_id(0)
        if cfg and cfg.smtp_username and cfg.smtp_password:
            return cfg
        return UserEmailSettingsModel(
            id=0,
            user_id=0,
            smtp_server=self.DEFAULT_SYSTEM_CONFIG['smtp_server'],
            smtp_port=self.DEFAULT_SYSTEM_CONFIG['smtp_port'],
            smtp_security=self.DEFAULT_SYSTEM_CONFIG['smtp_security'],
            smtp_username=self.DEFAULT_SYSTEM_CONFIG['smtp_username'],
            smtp_password=self.DEFAULT_SYSTEM_CONFIG['smtp_password'],
            sender_name=self.DEFAULT_SYSTEM_CONFIG['sender_name'],
            is_active=True
        )

    def save_system_config(
        self,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: str,
        smtp_password: str,
        sender_name: Optional[str] = None
    ) -> UserEmailSettingsModel:
        """Zapisuje lub aktualizuje globalną konfigurację konta systemowego (user_id=0)."""
        return self.save_or_update(
            user_id=0,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_security=smtp_security,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            sender_name=sender_name or 'Raport Produkcyjny AGRO'
        )

    def reset_system_config(self) -> UserEmailSettingsModel:
        """Resetuje konto systemowe do pierwotnych parametrów domyślnych."""
        return self.save_system_config(
            smtp_server=self.DEFAULT_SYSTEM_CONFIG['smtp_server'],
            smtp_port=self.DEFAULT_SYSTEM_CONFIG['smtp_port'],
            smtp_security=self.DEFAULT_SYSTEM_CONFIG['smtp_security'],
            smtp_username=self.DEFAULT_SYSTEM_CONFIG['smtp_username'],
            smtp_password=self.DEFAULT_SYSTEM_CONFIG['smtp_password'],
            sender_name=self.DEFAULT_SYSTEM_CONFIG['sender_name']
        )

    def get_by_user_id(self, user_id: int) -> Optional[UserEmailSettingsModel]:
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM uzytkownik_email_settings WHERE user_id = %s LIMIT 1"
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            if row:
                return UserEmailSettingsModel(
                    id=row['id'],
                    user_id=row['user_id'],
                    smtp_server=row['smtp_server'],
                    smtp_port=row['smtp_port'],
                    smtp_security=row['smtp_security'],
                    smtp_username=row['smtp_username'],
                    smtp_password=row['smtp_password'],
                    sender_name=row.get('sender_name'),
                    domyslni_odbiorcy=row.get('domyslni_odbiorcy'),
                    is_active=bool(row['is_active']),
                    created_at=row.get('created_at'),
                    updated_at=row.get('updated_at')
                )
            return None
        finally:
            conn.close()

    def save_or_update(
        self,
        user_id: int,
        smtp_server: str,
        smtp_port: int,
        smtp_security: str,
        smtp_username: str,
        smtp_password: str,
        sender_name: Optional[str] = None,
        domyslni_odbiorcy: Optional[str] = None
    ) -> UserEmailSettingsModel:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO uzytkownik_email_settings
                (user_id, smtp_server, smtp_port, smtp_security, smtp_username, smtp_password, sender_name, domyslni_odbiorcy, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    smtp_server = VALUES(smtp_server),
                    smtp_port = VALUES(smtp_port),
                    smtp_security = VALUES(smtp_security),
                    smtp_username = VALUES(smtp_username),
                    smtp_password = VALUES(smtp_password),
                    sender_name = VALUES(sender_name),
                    domyslni_odbiorcy = VALUES(domyslni_odbiorcy),
                    is_active = 1,
                    updated_at = NOW()
            """
            cursor.execute(query, (
                user_id,
                smtp_server.strip(),
                int(smtp_port),
                smtp_security.strip().upper(),
                smtp_username.strip(),
                smtp_password.strip(),
                sender_name.strip() if sender_name else None,
                domyslni_odbiorcy.strip() if domyslni_odbiorcy else None
            ))
            conn.commit()
            return self.get_by_user_id(user_id)
        finally:
            conn.close()

    def get_all_recipients(self) -> list:
        """Pobiera listę odbiorców ze słownika slownik_odbiorcy_email."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM slownik_odbiorcy_email WHERE aktywny = 1 ORDER BY grupa, nazwa")
            return cursor.fetchall() or []
        except Exception:
            return []
        finally:
            conn.close()

    def add_recipient(self, nazwa: str, email: str, grupa: str = 'Produkcja') -> bool:
        """Dodaje nowego odbiorcę do słownika slownik_odbiorcy_email."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS slownik_odbiorcy_email (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nazwa VARCHAR(100) NOT NULL,
                    email VARCHAR(150) NOT NULL,
                    grupa VARCHAR(50) DEFAULT 'Produkcja',
                    aktywny TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            cursor.execute(
                "INSERT INTO slownik_odbiorcy_email (nazwa, email, grupa, aktywny) VALUES (%s, %s, %s, 1)",
                (nazwa.strip(), email.strip(), grupa.strip() or 'Produkcja')
            )
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def delete_recipient(self, recipient_id: int) -> bool:
        """Usuwa odbiorcę ze słownika."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM slownik_odbiorcy_email WHERE id = %s", (recipient_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False
        finally:
            conn.close()

    def delete_by_user_id(self, user_id: int) -> bool:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM uzytkownik_email_settings WHERE user_id = %s", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
