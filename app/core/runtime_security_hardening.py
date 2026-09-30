"""Post-registration security guards for legacy runtime endpoints."""

from functools import wraps

from flask import current_app, jsonify, redirect, request, session


def _normalized_role() -> str:
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


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
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'success': False, 'error': 'unauthenticated'}), 401
            return redirect('/login')
        return original_view(*args, **kwargs)

    return guarded


def register_runtime_security_hardening(app) -> None:
    """Tighten legacy endpoints whose original checks are too broad."""
    endpoint = 'api.mqtt_simulate'
    original = app.view_functions.get(endpoint)
    if original is not None and not getattr(original, '_audit_admin_only', False):
        guarded = _admin_only(original)
        guarded._audit_admin_only = True
        app.view_functions[endpoint] = guarded

    # These two legacy printer views use ``'zalogowany' not in session`` in
    # their local decorator. Apply a strict outer guard until that large module
    # can be decomposed safely.
    for endpoint in (
        'admin.admin_ustawienia_drukarki',
        'admin.admin_ustawienia_logi_drukowania',
    ):
        original = app.view_functions.get(endpoint)
        if original is None or getattr(original, '_audit_truthy_login', False):
            continue
        guarded = _truthy_login_required(original)
        guarded._audit_truthy_login = True
        app.view_functions[endpoint] = guarded
