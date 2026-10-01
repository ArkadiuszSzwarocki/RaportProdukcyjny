"""Final runtime guards for audit findings that cross legacy endpoint boundaries."""

import ipaddress
import os
import socket
from functools import wraps

from flask import current_app, jsonify, request, session

from app.decorators import dynamic_role_required, login_required, masteradmin_required


def _normalized_role() -> str:
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


def _is_admin_session() -> bool:
    return _normalized_role() in {'admin', 'masteradmin'}


def _request_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form or {}


def _strict_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == '':
        return False
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError('invalid boolean')


def _masked_password(value) -> bool:
    clean = str(value or '').strip()
    return (
        not clean
        or clean.startswith('•')
        or clean == '********'
        or clean == '__SAVED_PASSWORD__'
    )


def _smtp_semantics_guard(original_view):
    """Prevent legacy ``bool('false')`` scope escalation and select system config safely."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        payload = _request_payload()
        raw_system = payload.get('is_system')
        try:
            is_system = _strict_bool(raw_system)
        except ValueError:
            return jsonify({'success': False, 'message': 'Nieprawidłowa wartość is_system.'}), 400

        # Legacy system.py uses bool(payload['is_system']); every non-empty form
        # string, including "false", therefore becomes True.  Do not pass such
        # ambiguous values into that implementation for non-administrators.
        if not _is_admin_session() and raw_system not in (None, '') and not isinstance(raw_system, bool):
            return jsonify({
                'success': False,
                'message': 'Pole is_system musi być wartością JSON true/false.',
            }), 400

        if request.endpoint == 'admin.api_email_test' and is_system and _is_admin_session():
            # The inner legacy/runtime test guard chooses a stored credential by
            # target_user_id.  For a system-scope masked-password test, force the
            # well-known system configuration id instead of the admin's account.
            json_payload = request.get_json(silent=True)
            if isinstance(json_payload, dict) and _masked_password(json_payload.get('smtp_password')):
                json_payload['target_user_id'] = 0

        return original_view(*args, **kwargs)

    return guarded


def _allowed_smtp_ports():
    raw = str(os.environ.get('SMTP_TEST_ALLOWED_PORTS', '25,465,587'))
    ports = set()
    for item in raw.split(','):
        try:
            port = int(item.strip())
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return ports or {25, 465, 587}


def _allowed_private_smtp_hosts():
    raw = str(os.environ.get('SMTP_ALLOWED_PRIVATE_HOSTS', ''))
    return {item.strip().lower().rstrip('.') for item in raw.split(',') if item.strip()}


def _smtp_target_is_safe(host, port):
    host = str(host or '').strip().rstrip('.')
    if not host:
        return False, 'Podaj serwer SMTP.'
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False, 'Nieprawidłowy port SMTP.'
    if port not in _allowed_smtp_ports():
        return False, 'Ten port SMTP nie jest dozwolony.'

    normalized_host = host.lower()
    if normalized_host in _allowed_private_smtp_hosts():
        return True, None
    if normalized_host == 'localhost' or normalized_host.endswith('.localhost'):
        return False, 'Lokalny adres SMTP nie jest dozwolony.'

    try:
        literal = ipaddress.ip_address(host.strip('[]'))
        addresses = {literal}
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            return False, 'Nie można bezpiecznie rozwiązać adresu serwera SMTP.'
        addresses = set()
        for item in resolved:
            try:
                addresses.add(ipaddress.ip_address(item[4][0]))
            except (ValueError, IndexError, TypeError):
                return False, 'Serwer SMTP zwrócił nieprawidłowy adres.'

    if not addresses:
        return False, 'Serwer SMTP nie ma poprawnego adresu.'
    if any(not address.is_global for address in addresses):
        return False, 'Prywatny lub lokalny adres SMTP wymaga jawnej konfiguracji administratora.'
    return True, None


def _smtp_test_network_guard(original_view):
    """Block authenticated SSRF through the SMTP connection-test endpoint."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        payload = _request_payload()
        safe, message = _smtp_target_is_safe(
            payload.get('smtp_server'),
            payload.get('smtp_port', 587),
        )
        if not safe:
            current_app.logger.warning(
                'Blocked unsafe SMTP test target host=%r port=%r user=%r',
                payload.get('smtp_server'),
                payload.get('smtp_port'),
                session.get('login'),
            )
            return jsonify({'success': False, 'message': message}), 400
        return original_view(*args, **kwargs)

    return guarded


def _credential_qr_guard(original_view):
    """Reject credential QR mode for JSON and form payloads."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        payload = _request_payload()
        if str(payload.get('mode') or '').strip().lower() == 'login':
            return jsonify({
                'success': False,
                'message': 'Drukowanie danych logowania w kodzie QR jest wyłączone.',
            }), 410
        return original_view(*args, **kwargs)

    return guarded


def _wrap_once(app, endpoint, wrapper, marker):
    original = app.view_functions.get(endpoint)
    if original is None:
        raise RuntimeError(f'Audit hardening expected missing endpoint: {endpoint}')
    if getattr(original, marker, False):
        return
    guarded = wrapper(original)
    setattr(guarded, marker, True)
    app.view_functions[endpoint] = guarded


def register_audit_phase3_hardening(app) -> None:
    """Install authorization, SMTP-network and input-semantics guards."""
    # Direct legacy replacements discard decorators attached to the old view
    # object. Restore explicit authorization on each replacement.
    _wrap_once(
        app,
        'magazyn_dostawy.dodruk_etykiet',
        login_required,
        '_audit_reprint_login_required',
    )
    _wrap_once(
        app,
        'admin.admin_zpl_test',
        masteradmin_required,
        '_audit_zpl_masteradmin_required',
    )
    _wrap_once(
        app,
        'admin.admin_printer_server_status',
        dynamic_role_required('ustawienia.system'),
        '_audit_printer_status_permission',
    )

    for endpoint in ('admin.api_email_test', 'admin.api_email_config_save', 'admin.api_email_config_reset'):
        _wrap_once(app, endpoint, _smtp_semantics_guard, '_audit_smtp_strict_scope')
    _wrap_once(
        app,
        'admin.api_email_test',
        _smtp_test_network_guard,
        '_audit_smtp_network_target',
    )

    _wrap_once(
        app,
        'admin.admin_qr_generator_drukuj',
        _credential_qr_guard,
        '_audit_no_credential_qr_any_payload',
    )

    # Fail startup rather than silently losing the break-glass database guard
    # after a future endpoint rename/refactor.
    db_switch = app.view_functions.get('admin.admin_secret_db_switch')
    if db_switch is None or not getattr(db_switch, '_audit_runtime_db_switch', False):
        raise RuntimeError('Runtime database switch is missing its audit guard.')
