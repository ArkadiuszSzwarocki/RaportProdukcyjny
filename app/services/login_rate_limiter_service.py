"""Login Rate Limiter Service.
Provides thread-safe in-memory rate limiting for login attempts to prevent brute-force attacks.
"""

import time
import threading
from typing import Tuple, Dict, List


class LoginRateLimiterService:
    """Thread-safe rate limiter for authentication endpoints."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 300):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lockout_seconds = lockout_seconds
        self._lock = threading.Lock()
        self._attempts: Dict[str, List[float]] = {}
        self._lockouts: Dict[str, float] = {}

    def _get_key(self, ip_address: str, username: str) -> str:
        clean_ip = (ip_address or '').strip().lower()
        clean_user = (username or '').strip().lower()
        return f"{clean_ip}:{clean_user}"

    def is_rate_limited(self, ip_address: str, username: str) -> Tuple[bool, int]:
        """Check if the given IP/username combination is currently rate-limited.
        
        Returns:
            Tuple[bool, int]: (is_limited, remaining_lockout_seconds)
        """
        key = self._get_key(ip_address, username)
        now = time.time()

        with self._lock:
            # Check active lockout
            lockout_expiry = self._lockouts.get(key, 0)
            if now < lockout_expiry:
                remaining = int(lockout_expiry - now) + 1
                return True, remaining

            # Cleanup expired lockout
            if key in self._lockouts:
                del self._lockouts[key]

            # Filter attempts inside the active window
            history = self._attempts.get(key, [])
            valid_history = [t for t in history if now - t < self._window_seconds]
            self._attempts[key] = valid_history

            if len(valid_history) >= self._max_attempts:
                # Trigger lockout
                self._lockouts[key] = now + self._lockout_seconds
                return True, self._lockout_seconds

            return False, 0

    def record_failed_attempt(self, ip_address: str, username: str) -> Tuple[bool, int]:
        """Record a failed login attempt and return if lockout was reached."""
        key = self._get_key(ip_address, username)
        now = time.time()

        with self._lock:
            history = self._attempts.get(key, [])
            valid_history = [t for t in history if now - t < self._window_seconds]
            valid_history.append(now)
            self._attempts[key] = valid_history

            if len(valid_history) >= self._max_attempts:
                self._lockouts[key] = now + self._lockout_seconds
                return True, self._lockout_seconds

            return False, 0

    def reset_attempts(self, ip_address: str, username: str) -> None:
        """Reset attempt history after successful login."""
        key = self._get_key(ip_address, username)
        with self._lock:
            self._attempts.pop(key, None)
            self._lockouts.pop(key, None)


# Singleton instance
login_rate_limiter = LoginRateLimiterService()
