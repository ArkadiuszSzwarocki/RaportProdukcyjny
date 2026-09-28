# File: app/core/crypto_utils.py
"""
Cryptographic utilities for secure storage of sensitive credentials (e.g. SMTP passwords).
Encryption uses a dedicated Fernet key supplied through the environment.
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet_instance(env_name: str = 'ENCRYPTION_KEY') -> Fernet:
    """Load a valid Fernet key from an explicitly configured environment variable."""
    key = (os.getenv(env_name) or '').strip()
    if not key:
        raise RuntimeError(f'Brak wymaganej zmiennej {env_name} dla szyfrowania danych.')
    try:
        return Fernet(key.encode('ascii'))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(f'Zmienna {env_name} nie jest poprawnym kluczem Fernet.') from exc


def _get_decryption_fernets():
    """Return the active key and optional explicitly configured previous keys."""
    keys = [_get_fernet_instance()]
    for key in (os.getenv('ENCRYPTION_KEY_PREVIOUS') or '').split(','):
        key = key.strip()
        if key:
            try:
                keys.append(Fernet(key.encode('ascii')))
            except (ValueError, UnicodeEncodeError) as exc:
                raise RuntimeError('ENCRYPTION_KEY_PREVIOUS zawiera niepoprawny klucz Fernet.') from exc
    # One-time compatibility path for ciphertext created before ENCRYPTION_KEY
    # existed. It is enabled only when an operator explicitly supplies the old
    # session secret; there is intentionally no built-in default value.
    legacy_secret = (os.getenv('LEGACY_SECRET_KEY') or '').strip()
    if legacy_secret:
        legacy_key = base64.urlsafe_b64encode(hashlib.sha256(legacy_secret.encode('utf-8')).digest())
        keys.append(Fernet(legacy_key))
    return keys


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypts a plaintext secret into an encoded ciphertext string."""
    if not plaintext:
        return plaintext
    if plaintext.startswith('enc::'):
        return plaintext
    encrypted_bytes = _get_fernet_instance().encrypt(plaintext.encode('utf-8'))
    return f"enc::{encrypted_bytes.decode('utf-8')}"


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypts an encrypted ciphertext back to plaintext. Safely handles legacy plaintext values."""
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith('enc::'):
        return ciphertext
    raw_token = ciphertext[5:].encode('utf-8')
    for fernet in _get_decryption_fernets():
        try:
            return fernet.decrypt(raw_token).decode('utf-8')
        except InvalidToken:
            continue
    raise RuntimeError('Nie można odszyfrować sekretu: skonfiguruj właściwy ENCRYPTION_KEY_PREVIOUS.')


def mask_secret(secret: Optional[str], length: int = 12) -> str:
    """Returns a secure masked representation of the secret for UI presentation."""
    if not secret:
        return ""
    return "•" * length
