# cspell:words szwarark boczkmar
"""Short, account-bound elevation checked before every authorized request."""
import math
import secrets
import time

from flask import Blueprint, current_app, jsonify, request, session

from app.core.audit import audit_log
from app.decorators import _normalize_role

ALLOWED_LOGINS = frozenset({'szwarark', 'boczkmar'})
DURATION_SECONDS = 600
_GRANT = '_temporary_masteradmin'


def eligible():
    """Only the two active supervisor accounts may use this switch."""
    return bool(session.get('zalogowany') and session.get('user_id')) and (
        str(session.get('login') or '').strip().casefold() in ALLOWED_LOGINS
        and _normalize_role(session.get('_account_role', session.get('rola'))) in {'lider', 'masteradmin'}
    )


def apply_temporary_role():
    """Keep the database role intact and expire elevated access on the server."""
    grant = session.get(_GRANT)
    if not eligible():
        if grant:
            session.pop(_GRANT, None)
            audit_log('MasterAdmin tymczasowy: odebrano dostęp', 'Zmiana konta lub roli bazowej')
        return
    now = time.time()
    active = False
    if isinstance(grant, dict):
        try:
            started = float(grant['started'])
            expires = float(grant['expires'])
            active = (
                math.isfinite(started) and math.isfinite(expires)
                and 0 < expires - started <= DURATION_SECONDS
                and started <= now < expires
                and grant['user_id'] == session.get('user_id')
                and grant['login'] == str(session.get('login')).casefold()
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            active = False
    session['rola'] = 'masteradmin' if active else 'lider'
    session['grupa'] = 'ALL'
    if grant and not active:
        session.pop(_GRANT, None)
        audit_log('MasterAdmin tymczasowy: powrót do lidera', 'Koniec ważności uprawnień')


def state():
    grant = session.get(_GRANT) or {}
    now = time.time()
    active = eligible() and session.get('rola') == 'masteradmin' and bool(grant)
    return {'eligible': eligible(), 'active': active, 'server_now': now,
            'expires_at': grant.get('expires') if active else None,
            'role': session.get('rola')}


def register_temporary_admin(app):
    blueprint = Blueprint('temporary_admin', __name__)

    @app.after_request
    def prevent_elevated_offline_pages(response):
        if state()['active']:
            response.headers['X-RP-Temporary-Admin'] = 'active'
        return response

    @app.context_processor
    def inject_switch():
        value = state()
        if value['eligible']:
            if not session.get('_temporary_admin_csrf'):
                session['_temporary_admin_csrf'] = secrets.token_urlsafe(32)
            value['csrf'] = session['_temporary_admin_csrf']
        return {'temporary_admin': value}

    @blueprint.get('/auth/temporary-masteradmin/status')
    def status():
        if not session.get('zalogowany'):
            return jsonify(success=False, message='Sesja wygasła.'), 401
        return jsonify(success=True, **state())

    @blueprint.post('/auth/temporary-masteradmin/<action>')
    def toggle(action):
        if not session.get('zalogowany'):
            return jsonify(success=False, message='Sesja wygasła.'), 401
        supplied = request.headers.get('X-CSRF-Token', '')
        expected = session.get('_temporary_admin_csrf', '')
        if not expected or not secrets.compare_digest(supplied, expected):
            return jsonify(success=False, message='Odśwież stronę i spróbuj ponownie.'), 403
        from app.core.security_hardening import _authoritative_role_sync
        if not _authoritative_role_sync(current_app, force=True):
            return jsonify(success=False, message='Nie można potwierdzić konta.'), 401
        apply_temporary_role()
        if not eligible():
            return jsonify(success=False, message='Przełącznik jest dostępny tylko dla wskazanych liderów.'), 403
        if action == 'enable':
            # Repeated clicks must not extend an existing ten-minute window.
            if not state()['active']:
                now = time.time()
                session[_GRANT] = {'started': now, 'expires': now + DURATION_SECONDS,
                                   'user_id': session['user_id'], 'login': str(session['login']).casefold()}
                apply_temporary_role()
                audit_log('MasterAdmin tymczasowy: włączono', 'Czas dostępu: 10 minut')
        elif action == 'disable':
            if session.pop(_GRANT, None):
                apply_temporary_role()
                audit_log('MasterAdmin tymczasowy: powrót do lidera', 'Wyłączono ręcznie')
        else:
            return jsonify(success=False, message='Nieprawidłowa operacja.'), 400
        return jsonify(success=True, **state())

    app.register_blueprint(blueprint)
