"""Post-registration security guards for legacy runtime endpoints."""

from functools import wraps

from flask import current_app, flash, jsonify, redirect, render_template, request, session


def _normalized_role() -> str:
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


def _wants_json() -> bool:
    return bool(request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json)


def _admin_only(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        explicit_test_override = bool(
            current_app.config.get('TESTING')
            and current_app.config.get('ALLOW_PRIVILEGED_TEST_ENDPOINTS')
        )
        if not explicit_test_override and _normalized_role() not in {'admin', 'masteradmin'}:
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
        flash(f'Błąd pobierania danych drukarek/kolejki: {exc}', 'error')
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
