"""Repository for user-level permission overrides (User ACL Overrides).
Allows granular overriding of role permissions for specific individual users.
"""

import threading
import time
from typing import Dict, Optional, Any
from app.core.database import get_db_connection


class UserPermissionOverrideRepository:
    """Handles CRUD operations for per-user permission overrides."""

    _overrides_cache: Dict[tuple, tuple] = {}
    _overrides_lock = threading.Lock()
    _OVERRIDES_TTL_S = 15.0

    @classmethod
    def _cache_scope_db(cls) -> str:
        try:
            from app.core.database import get_active_database_name
            return str(get_active_database_name() or 'default')
        except Exception:
            return 'default'

    @classmethod
    def _is_testing_env(cls) -> bool:
        try:
            from flask import current_app, has_app_context
            return bool(has_app_context() and current_app.config.get('TESTING'))
        except Exception:
            return False

    @classmethod
    def _invalidate_user_cache(cls, user_id: int) -> None:
        if not user_id:
            return
        uid = int(user_id)
        with cls._overrides_lock:
            stale_keys = [k for k in cls._overrides_cache if k[1] == uid]
            for k in stale_keys:
                cls._overrides_cache.pop(k, None)
        try:
            from flask import g, has_request_context
            if has_request_context():
                req_cache = getattr(g, '_user_overrides_by_user', None)
                if isinstance(req_cache, dict):
                    req_cache.pop(uid, None)
        except Exception:
            pass

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

        Uses per-request memoization (and a short invalidated TTL cache outside tests)
        so template loops calling role_has_access() dozens of times do not open one DB
        connection per check.
        """
        if not user_id or not page_key:
            return None

        uid = int(user_id)
        req_cache = None
        try:
            from flask import g, has_request_context
            if has_request_context():
                req_cache = getattr(g, '_user_overrides_by_user', None)
                if req_cache is None:
                    req_cache = {}
                    g._user_overrides_by_user = req_cache
                if uid in req_cache:
                    return req_cache[uid].get(page_key)
        except Exception:
            req_cache = None

        use_ttl_cache = not cls._is_testing_env()
        cache_key = (cls._cache_scope_db(), uid)
        if use_ttl_cache:
            now = time.monotonic()
            with cls._overrides_lock:
                entry = cls._overrides_cache.get(cache_key)
                if entry and (now - entry[0]) < cls._OVERRIDES_TTL_S:
                    overrides = entry[1]
                    if req_cache is not None:
                        req_cache[uid] = overrides
                    return overrides.get(page_key)

        overrides = cls.get_user_overrides(uid, strict=False)
        if req_cache is not None:
            req_cache[uid] = overrides
        if use_ttl_cache:
            with cls._overrides_lock:
                cls._overrides_cache[cache_key] = (time.monotonic(), overrides)
        return overrides.get(page_key)

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
