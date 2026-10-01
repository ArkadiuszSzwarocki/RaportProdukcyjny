"""Central security hardening that applies consistently across blueprints."""

import os
import time

from flask import jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from app.core.database import get_db_connection


_FORWARDED_ENV_KEYS = (
    'HTTP_X_FORWARDED_FOR',
    'HTTP_X_FORWARDED_PROTO',
    'HTTP_X_FORWARDED_HOST',
    'HTTP_X_FORWARDED_PORT',
    'HTTP_X_FORWARDED_PREFIX',
)
_PRIVILEGED_ROLES = {'admin', 'masteradmin', 'zarzad', 'lider'}


class StripForwardedHeadersMiddleware:
    """Hide raw forwarding headers from Flask after trusted proxy processing."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        for key in _FORWARDED_ENV_KEYS:
            environ.pop(key, None)
        return self.app(environ, start_response)


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def apply_proxy_policy(app):
    """Trust a configured proxy, then remove raw spoofable forwarding headers."""
    stripped_app = StripForwardedHeadersMiddleware(app.wsgi_app)
    if _env_bool('TRUST_PROXY_HEADERS', False):
        hops = max(1, int(os.environ.get('TRUSTED_PROXY_HOPS', '1')))
        app.wsgi_app = ProxyFix(
            stripped_app,
            x_for=hops,
            x_proto=hops,
            x_host=hops,
            x_prefix=hops,
        )
    else:
        app.wsgi_app = stripped_app


def register_legacy_secret_rejection(app):
    """Reject credentials that older clients attempted to put in URLs."""

    @app.before_request
    def _reject_query_string_secrets():
        if 'print_token' in request.args:
            return jsonify({
                'success': False,
                'error': 'Query-string print tokens are no longer supported.',
            }), 400
        return None


def _authoritative_role_sync(app, *, force=False):
    """Synchronize session privileges from the active database record.

    This function is intentionally fail-closed. A cookie is never allowed to
    retain a privileged role when the authoritative account record cannot be
    verified. ``force=True`` is used after login so the database role wins
    before Flask serializes the session cookie into the response.
    """
    if app.config.get('TESTING'):
        return True
    if not session.get('zalogowany'):
        return True

    user_id = session.get('user_id')
    login = str(session.get('login') or '').strip()
    if not user_id or not login:
        session.clear()
        return False

    now = time.time()
    last_check = float(session.get('_role_integrity_checked_at') or 0)
    if not force and now - last_check < 30:
        return True

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rola, grupa, COALESCE(is_active, 1) FROM uzytkownicy "
            "WHERE id = %s AND login = %s LIMIT 1",
            (user_id, login),
        )
        row = cursor.fetchone()
        if not row or int(row[2] or 0) != 1:
            session.clear()
            return False

        db_role = str(row[0] or '').lower().strip()
        db_group = str(row[1] or '').strip()
        if not db_role:
            session.clear()
            return False

        session['rola'] = db_role
        session['grupa'] = 'ALL' if db_role in _PRIVILEGED_ROLES else db_group
        session['_role_integrity_checked_at'] = now

        tracking_id = session.get('session_tracking_id')
        if tracking_id:
            cursor.execute(
                "UPDATE aktywne_sesje SET rola = %s WHERE session_id = %s AND user_id = %s",
                (db_role, tracking_id, user_id),
            )
            conn.commit()
        return True
    except Exception as exc:
        app.logger.warning('Role integrity check failed closed for user %s: %s', user_id, exc)
        session.clear()
        return False
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def register_role_integrity_check(app):
    """Keep role/group information tied to the active database account."""

    @app.before_request
    def _normalize_legacy_logged_in_flag():
        # Several legacy modules historically checked only whether the key was
        # present. Removing a false flag before route decorators run makes those
        # checks fail safely without retaining stale role/group information.
        if 'zalogowany' in session and not bool(session.get('zalogowany')):
            session.clear()
        return None

    @app.before_request
    def _sync_authenticated_role_before_request():
        _authoritative_role_sync(app, force=False)
        return None

    @app.after_request
    def _sync_authenticated_role_before_cookie(response):
        # before_request runs before the login view populates the session. Force
        # one authoritative lookup only after a successful login submission so
        # a legacy login-specific role override can never reach the cookie.
        if (
            request.endpoint == 'auth.login'
            and request.method == 'POST'
            and session.get('zalogowany')
        ):
            _authoritative_role_sync(app, force=True)
        return response


def current_client_ip():
    """Return the WSGI client address after the configured proxy policy."""
    return request.remote_addr or 'unknown'
