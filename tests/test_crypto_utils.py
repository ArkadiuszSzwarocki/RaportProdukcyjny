from cryptography.fernet import Fernet
import pytest

from app.core.crypto_utils import decrypt_secret, encrypt_secret


def test_encrypt_secret_requires_dedicated_key(monkeypatch):
    monkeypatch.delenv('ENCRYPTION_KEY', raising=False)

    with pytest.raises(RuntimeError, match='ENCRYPTION_KEY'):
        encrypt_secret('smtp-password')


def test_encrypt_secret_round_trip_with_dedicated_key(monkeypatch):
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())

    ciphertext = encrypt_secret('smtp-password')

    assert ciphertext.startswith('enc::')
    assert decrypt_secret(ciphertext) == 'smtp-password'


def test_decrypt_secret_accepts_explicit_previous_key(monkeypatch):
    previous_key = Fernet.generate_key()
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('ENCRYPTION_KEY_PREVIOUS', previous_key.decode())
    legacy_ciphertext = 'enc::' + Fernet(previous_key).encrypt(b'old-password').decode()

    assert decrypt_secret(legacy_ciphertext) == 'old-password'


def test_decrypt_secret_accepts_explicit_legacy_session_secret(monkeypatch):
    import base64
    import hashlib

    old_session_secret = 'old-session-secret'
    legacy_key = base64.urlsafe_b64encode(hashlib.sha256(old_session_secret.encode()).digest())
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('LEGACY_SECRET_KEY', old_session_secret)
    legacy_ciphertext = 'enc::' + Fernet(legacy_key).encrypt(b'old-password').decode()

    assert decrypt_secret(legacy_ciphertext) == 'old-password'
