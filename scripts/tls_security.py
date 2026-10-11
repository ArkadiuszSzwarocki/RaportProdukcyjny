"""Reject TLS keys exposed in this repository's history, including renamed copies."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import serialization


# SHA-256 of PUBLIC SubjectPublicKeyInfo, never private key material.
EXPOSED_PUBLIC_KEYS = frozenset({
    '631ccd11e93d0ca7822bebd61b57bc12aa2d24ca97203d2942771aefea523f5c',
    '8453835f1ab86f41379f22329bee5f4e9b656878ec39f7f0b318fa506eb88f37',
})


def _public_fingerprint(key):
    encoded = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(encoded).hexdigest()


def validate_tls_files(cert_path, key_path):
    """Require a fresh matching key/certificate pair; do not return any key bytes."""
    certificate = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    cert_fingerprint = _public_fingerprint(certificate.public_key())
    if cert_fingerprint in EXPOSED_PUBLIC_KEYS:
        raise ValueError('TLS key was exposed in Git history. Replace the key and certificate.')
    private_key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    key_fingerprint = _public_fingerprint(private_key.public_key())
    if key_fingerprint in EXPOSED_PUBLIC_KEYS:
        raise ValueError('TLS key was exposed in Git history. Replace the key and certificate.')
    if key_fingerprint != cert_fingerprint:
        raise ValueError('TLS certificate and private key do not match.')
    now = datetime.now(timezone.utc)
    if not certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc:
        raise ValueError('TLS certificate is outside its validity period.')
