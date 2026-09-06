"""Repository for user-level permission overrides (User ACL Overrides).
Allows granular overriding of role permissions for specific individual users.
"""

from typing import Dict, Optional, Any
from app.core.database import get_db_connection


class UserPermissionOverrideRepository:
    """Handles CRUD operations for per-user permission overrides."""

    @staticmethod
    def get_user_overrides(user_id: int) -> Dict[str, Dict[str, bool]]:
        """Fetch all permission overrides for a specific user.
        
        Returns:
            Dict[str, Dict[str, bool]]: Mapping of page_key -> {'access': bool, 'readonly': bool}
        """
        if not user_id:
            return {}

        conn = None
        overrides: Dict[str, Dict[str, bool]] = {}
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT page_key, access, readonly
                FROM uzytkownicy_uprawnienia
                WHERE user_id = %s
                """,
                (user_id,)
            )
            rows = cursor.fetchall()
            for row in rows:
                overrides[row['page_key']] = {
                    'access': bool(row['access']),
                    'readonly': bool(row['readonly'])
                }
            cursor.close()
            conn.close()
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return overrides

    @staticmethod
    def get_user_override(user_id: int, page_key: str) -> Optional[Dict[str, bool]]:
        """Fetch specific page override for a user, or None if no override is defined."""
        if not user_id or not page_key:
            return None

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT access, readonly
                FROM uzytkownicy_uprawnienia
                WHERE user_id = %s AND page_key = %s
                LIMIT 1
                """,
                (user_id, page_key)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                return {
                    'access': bool(row['access']),
                    'readonly': bool(row['readonly'])
                }
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        return None

    @staticmethod
    def set_user_override(user_id: int, page_key: str, access: bool, readonly: bool = False) -> bool:
        """Create or update a permission override for a user."""
        if not user_id or not page_key:
            return False

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO uzytkownicy_uprawnienia (user_id, page_key, access, readonly)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE access = VALUES(access), readonly = VALUES(readonly)
                """,
                (user_id, page_key, 1 if access else 0, 1 if readonly else 0)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception:
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            return False

    @staticmethod
    def delete_user_override(user_id: int, page_key: str) -> bool:
        """Remove an individual permission override for a user (reverting to role default)."""
        if not user_id or not page_key:
            return False

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM uzytkownicy_uprawnienia WHERE user_id = %s AND page_key = %s",
                (user_id, page_key)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception:
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            return False

    @staticmethod
    def clear_user_overrides(user_id: int) -> bool:
        """Remove all permission overrides for a user."""
        if not user_id:
            return False

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM uzytkownicy_uprawnienia WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception:
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            return False


# Singleton instance
user_permission_override_repository = UserPermissionOverrideRepository()
