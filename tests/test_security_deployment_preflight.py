"""Deployment checks fail closed and cannot disclose secret values."""
import json
from flask import Flask
import pytest
from scripts.security_preflight import inspect_environment
from app.core.factory import _configure_sessions


def test_production_cookies_default_to_secure(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SESSION_COOKIE_SECURE', raising=False)
    monkeypatch.delenv('USE_SSL', raising=False)
    app = Flask(__name__)
    _configure_sessions(app)
    assert app.config['SESSION_COOKIE_SECURE'] is True


def test_production_cannot_explicitly_disable_secure_cookie(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'false')
    with pytest.raises(RuntimeError, match='HTTPS'):
        _configure_sessions(Flask(__name__))


def test_host_allowlist_blocks_other_hosts(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'testing')
    monkeypatch.setenv('TRUSTED_HOSTS', 'warehouse.company.invalid')
    app = Flask(__name__)
    _configure_sessions(app)
    app.add_url_rule('/', view_func=lambda: 'ok')
    client = app.test_client()
    assert client.get('/', base_url='https://warehouse.company.invalid').status_code == 200
    assert client.get('/', base_url='https://attacker.invalid').status_code == 400


def test_preflight_flags_missing_certificates_and_never_returns_credentials():
    secret = 'SECRET-VALUE-THAT-MUST-NEVER-BE-PRINTED'
    checks = inspect_environment({'SECRET_KEY': secret, 'DB_PASSWORD': secret,
                                  'FLASK_ENV': 'production', 'DB_SSL_DISABLED': 'true'})
    result = {entry['check']: entry['passed'] for entry in checks}
    assert result['database_tls'] is False
    assert result['database_certificate'] is False
    assert result['trusted_hosts'] is False
    assert secret not in json.dumps(checks)
