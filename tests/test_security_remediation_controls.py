"""Exercise proxy spoofing and aggregate login attempts without network writes."""
import pytest
from flask import Flask, request
from app.core.security_hardening import apply_proxy_policy
from app.services.login_rate_limiter_service import LoginRateLimiterService


@pytest.mark.parametrize('peer, expected', [
    ('127.0.0.1', '203.0.113.8|https'),
    ('192.0.2.5', '192.0.2.5|http'),
    ('invalid', 'invalid|http'),
])
def test_forwarding_requires_allowlisted_socket_peer(monkeypatch, peer, expected):
    monkeypatch.setenv('TRUST_PROXY_HEADERS', 'true')
    monkeypatch.setenv('TRUSTED_PROXY_NETWORKS', '127.0.0.1/32,::1/128')
    monkeypatch.setenv('TRUSTED_PROXY_HOPS', '1')
    app = Flask(__name__)
    app.add_url_rule('/', view_func=lambda: f'{request.remote_addr}|{request.scheme}')
    apply_proxy_policy(app)
    response = app.test_client().get('/', environ_overrides={'REMOTE_ADDR': peer},
        headers={'X-Forwarded-For': '203.0.113.8', 'X-Forwarded-Proto': 'https'})
    assert response.text == expected


@pytest.mark.parametrize('networks', ['', '0.0.0.0/0', '::/0', 'not-a-network'])
def test_invalid_proxy_configuration_cannot_enable_trust(monkeypatch, networks):
    monkeypatch.setenv('TRUST_PROXY_HEADERS', 'true')
    monkeypatch.setenv('TRUSTED_PROXY_NETWORKS', networks)
    with pytest.raises(ValueError):
        apply_proxy_policy(Flask(__name__))


@pytest.fixture
def limiter(monkeypatch):
    def unavailable():
        raise RuntimeError('isolated fallback test')
    monkeypatch.setattr('app.services.login_rate_limiter_service.get_db_connection', unavailable)
    return LoginRateLimiterService(account_max_attempts=4, ip_max_attempts=6)


def test_distributed_failures_limit_the_account(limiter):
    for index in range(4):
        limiter.record_failed_attempt(f'192.0.2.{index}', 'User')
    assert limiter.is_rate_limited('198.51.100.7', ' user ')[0]
    assert not limiter.is_rate_limited('198.51.100.7', 'other')[0]


def test_password_spray_limits_source_address(limiter):
    for index in range(6):
        limiter.record_failed_attempt('192.0.2.5', f'user-{index}')
    assert limiter.is_rate_limited('192.0.2.5', 'new-user')[0]
    assert not limiter.is_rate_limited('192.0.2.6', 'new-user')[0]


def test_successful_login_does_not_clear_aggregate_failures(limiter):
    for index in range(4):
        limiter.record_failed_attempt(f'192.0.2.{index}', 'user')
    limiter.reset_attempts('192.0.2.0', 'user')
    assert limiter.is_rate_limited('192.0.2.9', 'user')[0]


def test_blocked_attempts_do_not_extend_lockout(limiter, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr('app.services.login_rate_limiter_service.time.time', lambda: clock[0])
    for index in range(4):
        limiter.record_failed_attempt(f'192.0.2.{index}', 'user')
    clock[0] = 1100.0
    limiter.record_failed_attempt('192.0.2.10', 'user')
    clock[0] = 1301.0
    assert not limiter.is_rate_limited('192.0.2.11', 'user')[0]


def test_report_only_policy_does_not_replace_enforced_policy(monkeypatch):
    from app.core.browser_security import register_browser_security_headers
    from app.core.middleware import add_security_headers
    monkeypatch.setenv('CSP_STRICT_REPORT_ONLY', 'true')
    app = Flask(__name__)
    app.add_url_rule('/', view_func=lambda: 'ok')
    app.after_request(add_security_headers(app))
    register_browser_security_headers(app)
    response = app.test_client().get('/')
    assert "'unsafe-inline'" in response.headers['Content-Security-Policy']
    report = response.headers['Content-Security-Policy-Report-Only']
    script = next(item for item in report.split(';') if item.strip().startswith('script-src'))
    assert 'unsafe-inline' not in script and 'unsafe-eval' not in script
