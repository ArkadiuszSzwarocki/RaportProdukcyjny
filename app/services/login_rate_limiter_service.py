"""Distributed login rate limiting backed by MySQL with an in-process fallback."""

import hashlib
import threading
import time
from typing import Dict, List, Tuple

from app.core.database import get_db_connection


class LoginRateLimiterService:
    """Rate limiter shared across Gunicorn workers through the application DB."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 300):
        self._max_attempts = int(max_attempts)
        self._window_seconds = int(window_seconds)
        self._lockout_seconds = int(lockout_seconds)
        self._lock = threading.Lock()
        self._schema_lock = threading.Lock()
        self._schema_ready = False
        self._attempts: Dict[str, List[float]] = {}
        self._lockouts: Dict[str, float] = {}

    def _get_key(self, ip_address: str, username: str) -> str:
        raw = f"{(ip_address or '').strip().lower()}:{(username or '').strip().lower()}"
        # Hashing keeps potentially sensitive usernames/IPs out of the rate-limit table.
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def _ensure_table(self, cursor) -> None:
        """Create the limiter table once per process instead of on every login."""
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS login_rate_limits (
                    rate_key CHAR(64) PRIMARY KEY,
                    attempt_count INT NOT NULL DEFAULT 0,
                    window_started_at DOUBLE NOT NULL DEFAULT 0,
                    lockout_until DOUBLE NOT NULL DEFAULT 0,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP
                )
                """
            )
            self._schema_ready = True

    def _memory_is_limited(self, key: str, now: float) -> Tuple[bool, int]:
        with self._lock:
            lockout_expiry = self._lockouts.get(key, 0)
            if now < lockout_expiry:
                return True, int(lockout_expiry - now) + 1
            self._lockouts.pop(key, None)
            history = [t for t in self._attempts.get(key, []) if now - t < self._window_seconds]
            self._attempts[key] = history
            if len(history) >= self._max_attempts:
                self._lockouts[key] = now + self._lockout_seconds
                return True, self._lockout_seconds
            return False, 0

    def _memory_record_failure(self, key: str, now: float) -> Tuple[bool, int]:
        with self._lock:
            history = [t for t in self._attempts.get(key, []) if now - t < self._window_seconds]
            history.append(now)
            self._attempts[key] = history
            if len(history) >= self._max_attempts:
                self._lockouts[key] = now + self._lockout_seconds
                return True, self._lockout_seconds
            return False, 0

    def is_rate_limited(self, ip_address: str, username: str) -> Tuple[bool, int]:
        key = self._get_key(ip_address, username)
        now = time.time()
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            self._ensure_table(cursor)
            cursor.execute(
                "SELECT attempt_count, window_started_at, lockout_until "
                "FROM login_rate_limits WHERE rate_key = %s FOR UPDATE",
                (key,),
            )
            row = cursor.fetchone()
            if not row:
                conn.commit()
                return False, 0

            lockout_until = float(row.get('lockout_until') or 0)
            if now < lockout_until:
                conn.commit()
                return True, int(lockout_until - now) + 1

            started = float(row.get('window_started_at') or 0)
            count = int(row.get('attempt_count') or 0)
            if not started or now - started >= self._window_seconds:
                cursor.execute(
                    "UPDATE login_rate_limits SET attempt_count = 0, window_started_at = %s, "
                    "lockout_until = 0 WHERE rate_key = %s",
                    (now, key),
                )
                conn.commit()
                return False, 0

            if count >= self._max_attempts:
                expiry = now + self._lockout_seconds
                cursor.execute(
                    "UPDATE login_rate_limits SET lockout_until = %s WHERE rate_key = %s",
                    (expiry, key),
                )
                conn.commit()
                return True, self._lockout_seconds

            conn.commit()
            return False, 0
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            # Database failures must not completely remove brute-force protection.
            return self._memory_is_limited(key, now)
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def record_failed_attempt(self, ip_address: str, username: str) -> Tuple[bool, int]:
        key = self._get_key(ip_address, username)
        now = time.time()
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            self._ensure_table(cursor)

            # Ensure the row exists atomically before locking it. Two workers
            # processing the first failure for the same account cannot race on
            # separate INSERT operations anymore.
            cursor.execute(
                "INSERT IGNORE INTO login_rate_limits "
                "(rate_key, attempt_count, window_started_at, lockout_until) "
                "VALUES (%s, 0, %s, 0)",
                (key, now),
            )
            cursor.execute(
                "SELECT attempt_count, window_started_at, lockout_until "
                "FROM login_rate_limits WHERE rate_key = %s FOR UPDATE",
                (key,),
            )
            row = cursor.fetchone() or {}

            current_lockout = float(row.get('lockout_until') or 0)
            if now < current_lockout:
                conn.commit()
                return True, int(current_lockout - now) + 1

            started = float(row.get('window_started_at') or 0)
            old_count = int(row.get('attempt_count') or 0)
            if not started or now - started >= self._window_seconds:
                started = now
                count = 1
            else:
                count = old_count + 1

            lockout_until = now + self._lockout_seconds if count >= self._max_attempts else 0
            cursor.execute(
                "UPDATE login_rate_limits SET attempt_count = %s, window_started_at = %s, "
                "lockout_until = %s WHERE rate_key = %s",
                (count, started, lockout_until, key),
            )
            conn.commit()
            if lockout_until:
                return True, self._lockout_seconds
            return False, 0
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return self._memory_record_failure(key, now)
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def reset_attempts(self, ip_address: str, username: str) -> None:
        key = self._get_key(ip_address, username)
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            self._ensure_table(cursor)
            cursor.execute("DELETE FROM login_rate_limits WHERE rate_key = %s", (key,))
            conn.commit()
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            with self._lock:
                self._attempts.pop(key, None)
                self._lockouts.pop(key, None)


login_rate_limiter = LoginRateLimiterService()
