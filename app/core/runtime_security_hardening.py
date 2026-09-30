"""Post-registration security guards for legacy runtime endpoints."""

import json
import os
import re
import uuid
from functools import wraps

from flask import current_app, flash, jsonify, redirect, render_template, request, session


def _normalized_role() -> str:
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


def _is_admin_session() -> bool:
    return _normalized_role() in {'admin', 'masteradmin'}


def _wants_json() -> bool:
    return bool(request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json)


def _env_bool(name, default=False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _admin_only(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        explicit_test_override = bool(
            current_app.config.get('TESTING')
            and current_app.config.get('ALLOW_PRIVILEGED_TEST_ENDPOINTS')
        )
        if not explicit_test_override and not _is_admin_session():
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403
        return original_view(*args, **kwargs)

    return guarded


def _truthy_login_required(original_view):
    """Reject legacy sessions where the login flag merely exists but is false."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        if not bool(session.get('zalogowany')):
            if _wants_json():
                return jsonify({'success': False, 'error': 'unauthenticated'}), 401
            return redirect('/login')
        return original_view(*args, **kwargs)

    return guarded


def _session_or_internal_print_required(original_view):
    """Allow a normal authenticated session or a valid header-only print token."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        from app.decorators import login_required_response

        denied = login_required_response()
        if denied is not None:
            return denied
        return original_view(*args, **kwargs)

    return guarded


def _reject_plaintext_credential_qr(original_view):
    """Never allow reusable account passwords to be rendered into printable QR codes."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        if bool(session.get('zalogowany')):
            payload = request.get_json(silent=True) or {}
            if str(payload.get('mode') or '').strip().lower() == 'login':
                return jsonify({
                    'success': False,
                    'message': (
                        'Drukowanie loginu i hasła w kodzie QR zostało wyłączone ze względów bezpieczeństwa.'
                    ),
                }), 410
        return original_view(*args, **kwargs)

    return guarded


def _masteradmin_runtime_db_switch(original_view):
    """Make global runtime database switching an explicit break-glass operation."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        if _normalized_role() != 'masteradmin':
            return jsonify({
                'success': False,
                'message': 'Przełączanie aktywnej bazy wymaga roli masteradmin.',
            }), 403
        if not _env_bool('ALLOW_RUNTIME_DB_SWITCH', False):
            return jsonify({
                'success': False,
                'message': 'Przełączanie aktywnej bazy jest wyłączone w tym środowisku.',
            }), 403
        return original_view(*args, **kwargs)

    return guarded


def _request_payload():
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form or {}


def _payload_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _masked_password(value) -> bool:
    clean = str(value or '').strip()
    return (
        not clean
        or clean.startswith('•')
        or clean == '********'
        or clean == '__SAVED_PASSWORD__'
    )


def _smtp_scope_guard(original_view):
    """Prevent ordinary users from modifying/testing another user's SMTP secret."""
    @wraps(original_view)
    def guarded(*args, **kwargs):
        if not bool(session.get('zalogowany')):
            return jsonify({'success': False, 'error': 'unauthenticated'}), 401

        payload = _request_payload()
        is_admin = _is_admin_session()
        session_user_id = session.get('user_id')
        target_raw = payload.get('target_user_id')
        target_id = None
        if target_raw not in (None, ''):
            try:
                target_id = int(target_raw)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Nieprawidłowy użytkownik.'}), 400

        if not is_admin:
            if not session_user_id:
                return jsonify({'success': False, 'message': 'Brak aktywnego konta użytkownika.'}), 403
            if _payload_bool(payload.get('is_system')):
                return jsonify({'success': False, 'message': 'Tylko administrator może zmieniać konto systemowe.'}), 403
            if target_id is not None and int(session_user_id) != target_id:
                return jsonify({'success': False, 'message': 'Nie możesz zmieniać konfiguracji innego użytkownika.'}), 403

        # A stored password may only be reused against the exact saved host and
        # username. Otherwise an attacker could redirect reusable credentials to
        # a server under their control during the connection test.
        if request.endpoint == 'admin.api_email_test' and _masked_password(payload.get('smtp_password')):
            effective_user_id = target_id if target_id is not None else session_user_id
            if effective_user_id is None:
                return jsonify({'success': False, 'message': 'Brak konta SMTP do testu.'}), 400
            try:
                from app.repositories.user_email_settings_repository import UserEmailSettingsRepository

                repo = UserEmailSettingsRepository()
                existing = (
                    repo.get_system_config()
                    if int(effective_user_id) == 0
                    else repo.get_by_user_id(int(effective_user_id))
                )
            except Exception:
                existing = None
            if not existing or not existing.smtp_password:
                return jsonify({'success': False, 'message': 'Brak zapisanego hasła SMTP do bezpiecznego testu.'}), 400

            requested_server = str(payload.get('smtp_server') or '').strip().lower()
            requested_username = str(payload.get('smtp_username') or '').strip().lower()
            saved_server = str(existing.smtp_server or '').strip().lower()
            saved_username = str(existing.smtp_username or '').strip().lower()
            if requested_server != saved_server or requested_username != saved_username:
                return jsonify({
                    'success': False,
                    'message': 'Przy użyciu zapisanego hasła nie można zmieniać serwera ani loginu SMTP.',
                }), 400

        return original_view(*args, **kwargs)

    return guarded


def _smtp_reset_guard(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        payload = _request_payload()
        if _payload_bool(payload.get('is_system')) and not _is_admin_session():
            return jsonify({'success': False, 'message': 'Tylko administrator może resetować konto systemowe.'}), 403
        return original_view(*args, **kwargs)

    return guarded


def _redact_sensitive_text(text: str) -> str:
    """Last-resort output redaction for diagnostic/log HTML responses."""
    if not text:
        return text
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED_EMAIL]', text)
    text = re.sub(
        r'(Authorization:\s*Bearer\s+)[A-Za-z0-9\-\._~\+/=]+',
        r'\1[REDACTED_TOKEN]',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[REDACTED_JWT]', text)
    text = re.sub(r'https?://[^\s/]+:[^@\s]+@', 'https://[REDACTED_AUTH]@', text)
    text = re.sub(
        r'(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)([^<\s,&]+)',
        r'\1\2[REDACTED]',
        text,
    )
    return text


def _redact_diagnostic_response(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        response = current_app.make_response(original_view(*args, **kwargs))
        if response.direct_passthrough:
            return response
        content_type = str(response.content_type or '').lower()
        if 'text/' not in content_type and 'json' not in content_type:
            return response
        try:
            response.set_data(_redact_sensitive_text(response.get_data(as_text=True)))
        except Exception:
            current_app.logger.exception('Diagnostic response redaction failed closed.')
            return jsonify({'success': False, 'message': 'Nie można bezpiecznie wyświetlić logów.'}), 500
        return response

    return guarded


def _printer_access_allowed() -> bool:
    if not bool(session.get('zalogowany')):
        return False
    try:
        from app.core.contexts import inject_role_permissions

        role_checker = inject_role_permissions().get('role_has_access')
    except Exception:
        role_checker = None
    group = str(session.get('grupa') or '').upper().strip()
    role = _normalized_role()
    return bool(
        (role_checker and (role_checker('ustawienia') or role_checker('magazyn.card')))
        or group == 'OSIP'
        or role in {'admin', 'masteradmin', 'magazynier', 'zarzad'}
    )


def secure_admin_printer_settings():
    """Render printer settings without opening arbitrary sockets from the web process."""
    if not bool(session.get('zalogowany')):
        if _wants_json():
            return jsonify({'success': False, 'error': 'unauthenticated'}), 401
        return redirect('/login')
    if not _printer_access_allowed():
        if _wants_json():
            return jsonify({'success': False, 'error': 'forbidden'}), 403
        flash('Brak uprawnień do modułu drukarek.', 'error')
        return redirect('/')

    from app.core.database import get_db_connection
    from app.services.print_server import get_printer

    printers = []
    jobs_stats = {'pending': 0, 'error': 0, 'done': 0, 'total_48h': 0}
    recent_jobs = []
    bridge_items = get_printer().list_network_printers()
    bridge_targets = {
        (str(item.get('name') or '').strip().lower(), str(item.get('ip') or '').strip())
        for item in bridge_items
        if isinstance(item, dict)
    }

    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM drukarki ORDER BY id ASC')
        printers = cursor.fetchall() or []

        cursor.execute("""
            SELECT
                SUM(CASE WHEN status IN ('PENDING', 'PRINTING') THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS error,
                SUM(CASE WHEN status = 'DONE' THEN 1 ELSE 0 END) AS done,
                COUNT(*) AS total_48h
            FROM print_jobs
            WHERE created_at >= NOW() - INTERVAL 2 DAY
        """)
        row = cursor.fetchone() or {}
        for key in jobs_stats:
            jobs_stats[key] = int(row.get(key) or 0)

        cursor.execute("""
            SELECT id, printer_name, printer_ip, status, retry_count,
                   error_message, created_at, updated_at
            FROM print_jobs
            WHERE created_at >= NOW() - INTERVAL 2 DAY
            ORDER BY id DESC
            LIMIT 200
        """)
        recent_jobs = cursor.fetchall() or []

        cursor.execute("""
            SELECT printer_name, printer_ip
            FROM print_jobs
            WHERE status = 'DONE' AND updated_at >= NOW() - INTERVAL 12 HOUR
        """)
        recent_success = {
            (str(item.get('printer_name') or '').strip().lower(), str(item.get('printer_ip') or '').strip())
            for item in (cursor.fetchall() or [])
        }

        for printer in printers:
            name = str(printer.get('nazwa') or '').strip().lower()
            target = str(printer.get('ip') or '').strip()
            if not target or target.upper() == 'USB' or target.lower().startswith('usb'):
                printer['tcp_online'] = True
                continue
            printer['tcp_online'] = (
                (name, target) in bridge_targets
                or (name, target) in recent_success
            )
    except Exception as exc:
        current_app.logger.exception('Could not load secure printer settings: %s', exc)
        flash('Błąd pobierania danych drukarek/kolejki.', 'error')
    finally:
        conn.close()

    return render_template(
        'ustawienia_drukarki.html',
        printers=printers,
        jobs_stats=jobs_stats,
        recent_jobs_48h=recent_jobs,
        recent_jobs=recent_jobs,
    )


def _wrap_once(app, endpoint, wrapper, marker):
    original = app.view_functions.get(endpoint)
    if original is None or getattr(original, marker, False):
        return
    guarded = wrapper(original)
    setattr(guarded, marker, True)
    app.view_functions[endpoint] = guarded


def _register_production_5xx_mask(app) -> None:
    """Mask route-local 5xx JSON bodies that would otherwise leak str(exception)."""
    @app.after_request
    def _mask_internal_5xx(response):
        if app.config.get('TESTING') or app.debug or response.status_code < 500:
            return response
        if not response.is_json:
            return response

        try:
            payload = response.get_json(silent=True)
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get('error_code'):
            return response

        ref = uuid.uuid4().hex[:8].upper()
        app.logger.error(
            'Masked route-local 5xx response [ERR-%s] from endpoint=%s path=%s',
            ref,
            request.endpoint,
            request.path,
        )
        safe_payload = {
            'success': False,
            'message': f'Wystąpił wewnętrzny błąd serwera. Kod błędu: ERR-{ref}',
            'error_code': f'ERR-{ref}',
        }
        response.set_data(json.dumps(safe_payload, ensure_ascii=False))
        response.content_type = 'application/json; charset=utf-8'
        return response


def register_runtime_security_hardening(app) -> None:
    """Tighten legacy endpoints whose original checks/transports are too broad."""
    _wrap_once(app, 'api.mqtt_simulate', _admin_only, '_audit_admin_only')

    if 'admin.admin_ustawienia_drukarki' in app.view_functions:
        app.view_functions['admin.admin_ustawienia_drukarki'] = secure_admin_printer_settings

    _wrap_once(
        app,
        'admin.admin_ustawienia_logi_drukowania',
        _truthy_login_required,
        '_audit_truthy_login',
    )

    # Legacy printer settings contained direct socket probes and a special-case
    # private IP. The route is replaced wholesale by secure_admin_printer_settings,
    # so no request can execute that source-controlled network exception.
    if app.view_functions.get('admin.admin_ustawienia_drukarki') is not secure_admin_printer_settings:
        raise RuntimeError('Legacy printer settings route remained active.')

    # Reusable passwords must never be encoded into printable QR labels.
    _wrap_once(
        app,
        'admin.admin_qr_generator_drukuj',
        _reject_plaintext_credential_qr,
        '_audit_no_credential_qr',
    )

    # Switching the global runtime database changes the security authority for
    # every worker. Keep it disabled by default and require masteradmin + opt-in.
    _wrap_once(
        app,
        'admin.admin_secret_db_switch',
        _masteradmin_runtime_db_switch,
        '_audit_runtime_db_switch',
    )

    # SMTP settings contain reusable credentials. Ordinary users may manage
    # only their own account; system/other-user scope and global recipients are
    # administrative operations.
    for endpoint in ('admin.api_email_test', 'admin.api_email_config_save'):
        _wrap_once(app, endpoint, _smtp_scope_guard, '_audit_smtp_scope')
    _wrap_once(app, 'admin.api_email_config_reset', _smtp_reset_guard, '_audit_smtp_reset')
    for endpoint in (
        'admin.api_email_recipient_add',
        'admin.api_email_recipient_delete',
        'admin.api_email_recipient_toggle',
    ):
        _wrap_once(app, endpoint, _admin_only, '_audit_smtp_recipients_admin')

    # Label previews can reveal current pallet/material data. Headless internal
    # printing remains possible only through the signed header token accepted by
    # login_required_response().
    for endpoint in (
        'magazyn_dostawy.podglad_etykiety',
        'magazyn_dostawy.podglad_etykiety_system',
        'magazyn_dostawy.podglad_etykiety_mix',
    ):
        _wrap_once(
            app,
            endpoint,
            _session_or_internal_print_required,
            '_audit_label_preview_auth',
        )

    # Error telemetry contains URLs, stack traces and usernames. It must not be
    # an unauthenticated public relay to the internal Watchdog service.
    for endpoint in ('api.log_frontend_error', 'api.log_watchdog_error'):
        _wrap_once(
            app,
            endpoint,
            _truthy_login_required,
            '_audit_telemetry_auth',
        )

    # Apply output redaction after all legacy log/search/raw-file branches have
    # rendered, so one forgotten branch cannot leak tokens, passwords or email.
    for endpoint in ('admin.admin_ustawienia_logs', 'admin.ustawienia_errors'):
        _wrap_once(
            app,
            endpoint,
            _redact_diagnostic_response,
            '_audit_diagnostic_redaction',
        )

    _register_production_5xx_mask(app)
