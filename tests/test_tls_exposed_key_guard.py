"""An exposed TLS key remains unsafe even with a new filename or certificate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from scripts import tls_security as tls


def fresh_pair(tmp_path, *, expired=False):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'warehouse.invalid')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=2))
                   .not_valid_after(now + timedelta(days=-1 if expired else 10))
                   .sign(key, hashes.SHA256()))
    cert_file, key_file = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_file, key_file, key


def test_repository_certificate_uses_exposed_key(tmp_path):
    certificate = Path(__file__).resolve().parents[1] / 'certs/cert.pem'
    with pytest.raises(ValueError, match='exposed'):
        tls.validate_tls_files(certificate, tmp_path / 'missing-key.pem')


def test_new_certificate_and_key_are_accepted(tmp_path):
    cert_file, key_file, _ = fresh_pair(tmp_path)
    tls.validate_tls_files(cert_file, key_file)


def test_renaming_key_and_reissuing_certificate_does_not_bypass_guard(tmp_path, monkeypatch):
    cert_file, key_file, key = fresh_pair(tmp_path)
    monkeypatch.setattr(tls, 'EXPOSED_PUBLIC_KEYS', {tls._public_fingerprint(key.public_key())})
    renamed = tmp_path / 'new-name.pem'
    key_file.rename(renamed)
    with pytest.raises(ValueError, match='exposed'):
        tls.validate_tls_files(cert_file, renamed)


def test_expired_certificate_rejected(tmp_path):
    cert_file, key_file, _ = fresh_pair(tmp_path, expired=True)
    with pytest.raises(ValueError, match='validity'):
        tls.validate_tls_files(cert_file, key_file)


def test_mismatched_key_rejected(tmp_path):
    cert_file, key_file, _ = fresh_pair(tmp_path)
    another = ec.generate_private_key(ec.SECP256R1())
    key_file.write_bytes(another.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with pytest.raises(ValueError, match='match'):
        tls.validate_tls_files(cert_file, key_file)
