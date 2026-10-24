"""Explicit office printer allowlist; no printer is enabled by default."""
import json
import os
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


def office_printers():
    configured = os.environ.get('OFFICE_PRINTERS_JSON')
    config_file = os.environ.get('OFFICE_PRINTERS_FILE')
    if not configured and config_file:
        configured = Path(config_file).read_text(encoding='utf-8-sig')
    raw = json.loads(configured or '{}')
    if not isinstance(raw, dict):
        raise ValueError('OFFICE_PRINTERS_JSON musi być obiektem JSON.')
    result = {}
    for key, value in raw.items():
        if not isinstance(value, dict) or value.get('enabled') is not True:
            continue
        name = str(value.get('windows_name') or '').strip()
        if not name or len(str(key)) > 80:
            raise ValueError('Wskaż nazwę kolejki Windows dla drukarki A4.')
        uri = str(value.get('ipp_uri') or '').strip()
        if uri:
            parsed = urlsplit(uri)
            address = ipaddress.ip_address(parsed.hostname or '')
            if (parsed.scheme not in ('ipp', 'http', 'https') or parsed.username or parsed.password
                    or not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast
                    or parsed.query or parsed.fragment):
                raise ValueError('IPP wymaga adresu IP drukarki w sieci lokalnej, bez hasła w URL.')
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError('Nieprawidłowy port IPP.')
        result[str(key)] = dict(label=str(value.get('label') or key)[:100], windows_name=name, ipp_uri=uri)
    return result
