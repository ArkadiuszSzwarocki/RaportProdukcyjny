"""Repository for user-level permission overrides (User ACL Overrides).
Allows granular overriding of role permissions for specific individual users.
"""

from typing import Dict, Optional

from flask import has_request_context, request
from app.core.database import get_db_connection


_REQUEST_CACHE_KEY = 'app.user_permission_overrides'


class UserPermissionOverrideRepository:
    """Handles CRUD operations for per-user permission overrides."""

    @staticmethod
    def _invalidate_user_cache(user_id: int) -> None:
        if has_request_context():
            request.environ.get(_REQUEST_CACHE_KEY, {}).pop(int(user_id), None)

    @staticmethod
    def get_user_overrides(user_id: int, strict: bool = False) -> Dict[str, Dict[str, bool]]:
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
            if strict:
                raise
        return overrides

    @classmethod
    def get_user_override(cls, user_id: int, page_key: str) -> Optional[Dict[str, bool]]:
        """Fetch specific page override for a user, or None if no override is defined.

        Read overrides once per request so subsequent requests see committed changes.
        """
        if not user_id or not page_key:
            return None

        uid = int(user_id)
        if not has_request_context():
            return cls.get_user_overrides(uid).get(page_key)

        req_cache = request.environ.setdefault(_REQUEST_CACHE_KEY, {})
        if uid not in req_cache:
            req_cache[uid] = cls.get_user_overrides(uid)
        return req_cache[uid].get(page_key)

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
            UserPermissionOverrideRepository._invalidate_user_cache(user_id)
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
            UserPermissionOverrideRepository._invalidate_user_cache(user_id)
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
            UserPermissionOverrideRepository._invalidate_user_cache(user_id)
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
