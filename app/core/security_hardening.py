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


def register_role_integrity_check(app):
    """Keep privileged role information tied to the active database record."""

    @app.before_request
    def _sync_authenticated_role():
        if app.config.get('TESTING'):
            return None
        if not session.get('zalogowany'):
            return None
        user_id = session.get('user_id')
        login = str(session.get('login') or '').strip()
        if not user_id or not login:
            return None

        now = time.time()
        last_check = float(session.get('_role_integrity_checked_at') or 0)
        if now - last_check < 30:
            return None

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rola, COALESCE(is_active, 1) FROM uzytkownicy "
                "WHERE id = %s AND login = %s LIMIT 1",
                (user_id, login),
            )
            row = cursor.fetchone()
            if not row or int(row[1] or 0) != 1:
                session.clear()
                return None

            db_role = str(row[0] or '').lower().strip()
            if db_role:
                session['rola'] = db_role
            session['_role_integrity_checked_at'] = now
        except Exception as exc:
            app.logger.warning('Role integrity check failed for user %s: %s', user_id, exc)
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
        return None


def current_client_ip():
    """Return the WSGI client address after the configured proxy policy."""
    return request.remote_addr or 'unknown'
