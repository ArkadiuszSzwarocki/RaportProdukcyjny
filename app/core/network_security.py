"""Network target validation for server-side outbound integrations."""

import ipaddress
import os
import socket


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


def smtp_target_allowed(host, port, security):
    """Validate an SMTP destination before any server-side connection is attempted."""
    host = str(host or '').strip().rstrip('.')
    security = str(security or 'SSL').strip().upper()
    try:
        port = int(port or 465)
    except (TypeError, ValueError):
        return False, 'Nieprawidłowy port SMTP.'

    if not host or len(host) > 253:
        return False, 'Nieprawidłowy serwer SMTP.'
    if port not in allowed_smtp_ports():
        return False, 'Ten port SMTP nie jest dozwolony.'
    if security not in {'SSL', 'TLS'} and not _env_bool('SMTP_ALLOW_PLAINTEXT', False):
        return False, 'Nieszyfrowane połączenia SMTP są wyłączone.'

    allowlisted = {
        item.strip().lower().rstrip('.')
        for item in os.environ.get('SMTP_ALLOWED_HOSTS', '').split(',')
        if item.strip()
    }
    if host.lower() in allowlisted:
        return True, ''

    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False, 'Nie można bezpiecznie rozpoznać serwera SMTP.'

    allow_private = _env_bool('SMTP_ALLOW_PRIVATE_HOSTS', False)
    for result in addresses:
        try:
            address = ipaddress.ip_address(result[4][0].split('%', 1)[0])
        except (ValueError, IndexError):
            return False, 'Nieprawidłowy adres serwera SMTP.'
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ) and not allow_private:
            return False, 'Prywatny adres SMTP wymaga jawnej allowlisty środowiskowej.'
    return True, ''
