"""Cryptographic token utilities for short-lived internal communications."""

import hashlib
import hmac
import time

from flask import current_app


_MAX_INTERNAL_TOKEN_TTL_SECONDS = 300


def _secret_bytes():
    secret = current_app.secret_key
    if not secret:
        raise RuntimeError('Brak skonfigurowanego SECRET_KEY dla tokenu wewnętrznego.')
    return secret.encode('utf-8') if isinstance(secret, str) else secret


def generate_internal_print_token(endpoint: str, expires_in_sec: int = 60) -> str:
    """Generate an endpoint-bound HMAC token valid for at most five minutes."""
    clean_endpoint = str(endpoint or '').strip()
    if not clean_endpoint.startswith('/'):
        raise ValueError('Internal token endpoint must be an absolute application path.')
    ttl = max(1, min(int(expires_in_sec or 60), _MAX_INTERNAL_TOKEN_TTL_SECONDS))
    expires_at = int(time.time()) + ttl
    data = f'{clean_endpoint}:{expires_at}'.encode('utf-8')
    signature = hmac.new(_secret_bytes(), data, hashlib.sha256).hexdigest()
    return f'{expires_at}:{signature}'


def verify_internal_print_token(endpoint: str, token: str) -> bool:
    """Verify endpoint binding, expiry, bounded TTL and signature."""
    clean_endpoint = str(endpoint or '').strip()
    if not clean_endpoint.startswith('/') or not token or ':' not in token:
        return False
    try:
        ts_str, signature = token.split(':', 1)
        expires_at = int(ts_str)
        now = time.time()
        if expires_at < now:
            return False
        if expires_at - now > _MAX_INTERNAL_TOKEN_TTL_SECONDS:
            return False
        data = f'{clean_endpoint}:{expires_at}'.encode('utf-8')
        expected = hmac.new(_secret_bytes(), data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False
