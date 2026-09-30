"""Post-registration security guards for legacy runtime endpoints."""

from functools import wraps

from flask import current_app, jsonify, session


def _normalized_role() -> str:
    return str(session.get('rola') or '').lower().replace(' ', '').replace('_', '').strip()


def _admin_only(original_view):
    @wraps(original_view)
    def guarded(*args, **kwargs):
        # Tests that genuinely need the simulator must opt in explicitly;
        # TESTING alone must never turn authorization off globally.
        explicit_test_override = bool(
            current_app.config.get('TESTING')
            and current_app.config.get('ALLOW_PRIVILEGED_TEST_ENDPOINTS')
        )
        if not explicit_test_override and _normalized_role() not in {'admin', 'masteradmin'}:
            return jsonify({'success': False, 'message': 'Brak uprawnień'}), 403
        return original_view(*args, **kwargs)

    return guarded


def register_runtime_security_hardening(app) -> None:
    """Tighten legacy endpoints whose original role checks are too broad."""
    endpoint = 'api.mqtt_simulate'
    original = app.view_functions.get(endpoint)
    if original is not None and not getattr(original, '_audit_admin_only', False):
        guarded = _admin_only(original)
        guarded._audit_admin_only = True
        app.view_functions[endpoint] = guarded
