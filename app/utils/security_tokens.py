"""
Cryptographic token utilities for secure internal communications (e.g. headless printing).
"""
import hmac
import hashlib
import time
from flask import current_app


def generate_internal_print_token(endpoint: str, expires_in_sec: int = 60) -> str:
    """Generate a cryptographic HMAC token for internal headless print rendering."""
    secret = current_app.secret_key or 'default-internal-secret'
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    expires_at = int(time.time()) + expires_in_sec
    data = f"{endpoint}:{expires_at}".encode('utf-8')
    signature = hmac.new(secret, data, hashlib.sha256).hexdigest()
    return f"{expires_at}:{signature}"


def verify_internal_print_token(endpoint: str, token: str) -> bool:
    """Verify validity, expiration, and signature of an internal print token."""
    if not token or ':' not in token:
        return False
    try:
        ts_str, signature = token.split(':', 1)
        expires_at = int(ts_str)
        if time.time() > expires_at:
            return False

        secret = current_app.secret_key or 'default-internal-secret'
        if isinstance(secret, str):
            secret = secret.encode('utf-8')
        data = f"{endpoint}:{expires_at}".encode('utf-8')
        expected = hmac.new(secret, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False
