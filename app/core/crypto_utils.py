# File: app/core/crypto_utils.py
"""
Cryptographic utilities for secure storage of sensitive credentials (e.g. SMTP passwords).
Uses Fernet (AES-128-CBC + HMAC-SHA256) with a deterministic master key derived from app secret.
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet_instance() -> Fernet:
    """Derives a 32-byte URL-safe base64 Fernet key from application environment secrets."""
    secret_seed = os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY') or 'agromes-production-crypto-seed-salt-2026'
    key_bytes = hashlib.sha256(secret_seed.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts a plaintext secret into an encoded ciphertext string."""
    if not plaintext:
        return plaintext
    if plaintext.startswith('enc::'):
        return plaintext
    try:
        f = _get_fernet_instance()
        encrypted_bytes = f.encrypt(plaintext.encode('utf-8'))
        return f"enc::{encrypted_bytes.decode('utf-8')}"
    except Exception:
        return plaintext


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts an encrypted ciphertext back to plaintext. Safely handles legacy plaintext values."""
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith('enc::'):
        return ciphertext
    try:
        raw_token = ciphertext[5:]
        f = _get_fernet_instance()
        decrypted_bytes = f.decrypt(raw_token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except (InvalidToken, Exception):
        return ciphertext


def mask_secret(secret: Optional[str], length: int = 12) -> str:
    """Returns a secure masked representation of the secret for UI presentation."""
    if not secret:
        return ""
    return "•" * length
