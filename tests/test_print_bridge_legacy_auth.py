from unittest.mock import Mock, patch

import pytest

from app.services.print_server import PrintServer


def test_bearer_remains_default(monkeypatch):
    monkeypatch.delenv('PRINTER_BRIDGE_AUTH_MODE', raising=False)
    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'test-only-token')
    assert PrintServer()._bridge_headers() == {'Authorization': 'Bearer test-only-token'}


@pytest.mark.parametrize('url', ['http://127.0.0.1:18083', 'https://bridge.example.test'])
def test_explicit_legacy_mode_sends_only_expected_header(monkeypatch, url):
    monkeypatch.setenv('PRINTER_BRIDGE_AUTH_MODE', 'legacy_api_token')
    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'test-only-token')
    monkeypatch.setenv('PRINTER_BRIDGE_URL', url)
    response = Mock(status_code=200)
    with patch('app.services.print_server.requests.request', return_value=response) as request:
        service = PrintServer()
        service._request_bridge('GET', '/printers')
    assert request.call_args.kwargs['headers'] == {'X-API-TOKEN': 'test-only-token'}
    assert request.call_args.kwargs['verify'] is True
    assert request.call_args.kwargs['allow_redirects'] is False


def test_legacy_mode_never_sends_token_over_remote_http(monkeypatch):
    monkeypatch.setenv('PRINTER_BRIDGE_AUTH_MODE', 'legacy_api_token')
    monkeypatch.setenv('PRINTER_BRIDGE_TOKEN', 'test-only-token')
    monkeypatch.setenv('PRINTER_BRIDGE_URL', 'http://bridge.example.test:3001')
    with patch('app.services.print_server.requests.request') as request:
        with pytest.raises(ValueError, match='HTTPS'):
            PrintServer()._request_bridge('GET', '/printers')
    request.assert_not_called()


def test_unknown_auth_mode_fails_explicitly(monkeypatch):
    monkeypatch.setenv('PRINTER_BRIDGE_AUTH_MODE', 'unknown')
    with pytest.raises(ValueError, match='AUTH_MODE'):
        PrintServer()
