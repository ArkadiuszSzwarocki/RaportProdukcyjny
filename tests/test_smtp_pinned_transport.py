"""SMTP must dial the vetted DNS result and preserve TLS hostname checks."""
import socket
import ssl
from unittest.mock import MagicMock

import pytest
from app.core import network_security as net


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch):
    for key in ('SMTP_ALLOWED_HOSTS', 'SMTP_ALLOWED_PRIVATE_HOSTS',
                'SMTP_ALLOW_PRIVATE_HOSTS', 'SMTP_ALLOW_PLAINTEXT', 'SMTP_ALLOWED_PORTS'):
        monkeypatch.delenv(key, raising=False)


def address(ip='8.8.8.8', port=465):
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, port))


def fake_greeting(self, host, port):
    self.sock = self._get_socket(host, port, self.timeout)  # pylint: disable=protected-access
    return 220, b'ready'


def test_rebinding_cannot_change_dialed_address(monkeypatch):
    resolve = MagicMock(side_effect=[[address()], [address('127.0.0.1')]])
    connection = MagicMock()
    context = MagicMock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
    monkeypatch.setattr(net.socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(net.socket, 'socket', MagicMock(return_value=connection))
    monkeypatch.setattr(net._PinnedSMTP, 'connect', fake_greeting)
    client = net.secure_smtp_connection('mail.example.com', 465, 'SSL', context=context)
    resolve.assert_called_once()
    connection.connect.assert_called_once_with(('8.8.8.8', 465))
    context.wrap_socket.assert_called_once_with(connection, server_hostname='mail.example.com')
    assert client._host == 'mail.example.com'  # pylint: disable=protected-access


@pytest.mark.parametrize('addresses', [[], [address('127.0.0.1')],
                                      [address(), address('10.0.0.1')]])
def test_invalid_or_mixed_dns_fails_before_socket(monkeypatch, addresses):
    monkeypatch.setattr(net.socket, 'getaddrinfo', lambda *a, **k: addresses)
    dial = MagicMock()
    monkeypatch.setattr(net.socket, 'socket', dial)
    with pytest.raises(ValueError):
        net.secure_smtp_connection('mail.example.com', 465, 'SSL')
    dial.assert_not_called()


def test_explicit_private_host_still_resolves_and_pins(monkeypatch):
    monkeypatch.setenv('SMTP_ALLOWED_PRIVATE_HOSTS', 'mail.internal')
    resolve = MagicMock(return_value=[address('10.0.0.5', 587)])
    connection = MagicMock()
    monkeypatch.setattr(net.socket, 'getaddrinfo', resolve)
    monkeypatch.setattr(net.socket, 'socket', MagicMock(return_value=connection))
    monkeypatch.setattr(net._PinnedSMTP, 'connect', fake_greeting)
    monkeypatch.setattr(net._PinnedSMTP, 'ehlo', MagicMock())
    starttls = MagicMock()
    monkeypatch.setattr(net._PinnedSMTP, 'starttls', starttls)
    client = net.secure_smtp_connection('mail.internal', 587, 'TLS')
    resolve.assert_called_once()
    connection.connect.assert_called_once_with(('10.0.0.5', 587))
    assert client._host == 'mail.internal'  # pylint: disable=protected-access
    starttls.assert_called_once()
    assert starttls.call_args.kwargs['context'].check_hostname is True


def test_insecure_tls_context_rejected(monkeypatch):
    monkeypatch.setattr(net.socket, 'getaddrinfo', lambda *a, **k: [address()])
    with pytest.raises(ValueError, match='certificate'):
        net.secure_smtp_connection('mail.example.com', 465, 'SSL',
                                   context=MagicMock(check_hostname=False))


def test_tls_failure_closes_socket(monkeypatch):
    connection = MagicMock()
    context = MagicMock(check_hostname=True, verify_mode=ssl.CERT_REQUIRED)
    context.wrap_socket.side_effect = ssl.SSLError('certificate mismatch')
    monkeypatch.setattr(net.socket, 'getaddrinfo', lambda *a, **k: [address()])
    monkeypatch.setattr(net.socket, 'socket', MagicMock(return_value=connection))
    monkeypatch.setattr(net._PinnedSMTP, 'connect', fake_greeting)
    with pytest.raises(ssl.SSLError):
        net.secure_smtp_connection('mail.example.com', 465, 'SSL', context=context)
    connection.close.assert_called_once()
