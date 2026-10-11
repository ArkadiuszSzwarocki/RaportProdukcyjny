"""Network target validation for server-side outbound integrations."""

import ipaddress
import os
import socket
import smtplib
import ssl


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def allowed_smtp_ports():
    raw = os.environ.get('SMTP_ALLOWED_PORTS', '25,465,587')
    ports = set()
    for value in raw.split(','):
        try:
            port = int(value.strip())
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return ports or {25, 465, 587}


def _resolve_smtp_target(host, port, security):
    """Resolve and validate every address; the transport must use this result."""
    host = str(host or '').strip().rstrip('.')
    security = str(security or 'SSL').strip().upper()
    try:
        port = int(port or 465)
    except (TypeError, ValueError):
        raise ValueError('Nieprawidłowy port SMTP.')

    if not host or len(host) > 253:
        raise ValueError('Nieprawidłowy serwer SMTP.')
    if port not in allowed_smtp_ports():
        raise ValueError('Ten port SMTP nie jest dozwolony.')
    if security not in {'SSL', 'TLS', 'NONE'}:
        raise ValueError('Nieprawidłowy tryb zabezpieczeń SMTP.')
    if security not in {'SSL', 'TLS'} and not _env_bool('SMTP_ALLOW_PLAINTEXT', False):
        raise ValueError('Nieszyfrowane połączenia SMTP są wyłączone.')

    allowlisted = {
        item.strip().lower().rstrip('.')
        for item in os.environ.get('SMTP_ALLOWED_HOSTS', '').split(',')
        if item.strip()
    }
    allowlisted.update(item.strip().lower().rstrip('.') for item in
                       os.environ.get('SMTP_ALLOWED_PRIVATE_HOSTS', '').split(',') if item.strip())

    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError('Nie można bezpiecznie rozpoznać serwera SMTP.') from None

    if not addresses:
        raise ValueError('Serwer SMTP nie ma poprawnego adresu.')

    allow_private = _env_bool('SMTP_ALLOW_PRIVATE_HOSTS', False) or host.lower() in allowlisted
    for result in addresses:
        try:
            address = ipaddress.ip_address(result[4][0].split('%', 1)[0])
        except (ValueError, IndexError, TypeError):
            raise ValueError('Nieprawidłowy adres serwera SMTP.') from None
        if result[0] not in {socket.AF_INET, socket.AF_INET6} or result[4][1] != port:
            raise ValueError('Nieprawidłowy adres serwera SMTP.')
        if (
            not address.is_global
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ) and not allow_private:
            raise ValueError('Prywatny adres SMTP wymaga jawnej allowlisty środowiskowej.')
    return host, port, addresses


def smtp_target_allowed(host, port, security):
    """Preflight only; secure_smtp_connection validates and pins at connection time."""
    try:
        _resolve_smtp_target(host, port, security)
    except ValueError as exc:
        return False, str(exc)
    return True, ''


class _PinnedSMTP(smtplib.SMTP):
    """Keep SMTP's original hostname for TLS, but dial validated socket addresses."""

    def _get_socket(self, host, port, timeout):
        last_error = None
        for family, socktype, proto, _, address in self.validated_addresses:
            connection = socket.socket(family, socktype, proto)
            try:
                connection.settimeout(timeout)
                connection.connect(address)
                return connection
            except OSError as exc:
                connection.close()
                last_error = exc
        raise last_error or OSError('SMTP connection failed')


class _PinnedSMTPSSL(_PinnedSMTP):
    def _get_socket(self, host, port, timeout):
        connection = super()._get_socket(host, port, timeout)
        try:
            return self.tls_context.wrap_socket(connection, server_hostname=host)
        except Exception:
            connection.close()
            raise


def secure_smtp_connection(host, port, security, *, timeout=15, context=None):
    """Open SMTP without resolving DNS a second time or disabling TLS verification."""
    host, port, addresses = _resolve_smtp_target(host, port, security)
    context = context or ssl.create_default_context()
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ValueError('SMTP requires certificate and hostname verification')
    security = str(security or 'SSL').strip().upper()
    use_ssl = security == 'SSL'
    client = _PinnedSMTPSSL(timeout=timeout) if use_ssl else _PinnedSMTP(timeout=timeout)
    client.validated_addresses = addresses
    client.tls_context = context
    # smtplib.starttls uses _host for SNI and certificate hostname validation.
    client._host = host  # pylint: disable=protected-access
    try:
        code, message = client.connect(host, port)
        if code != 220:
            raise smtplib.SMTPConnectError(code, message)
        if security == 'TLS':
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        return client
    except Exception:
        client.close()
        raise
