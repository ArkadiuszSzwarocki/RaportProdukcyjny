"""Application request/response middleware."""

import os
import re
import time
from urllib.parse import urlparse

from flask import current_app, jsonify, redirect, render_template, request, session, url_for

from app.db import (
    deactivate_active_session,
    ensure_session_tracking_id,
    get_db_connection,
    is_session_active,
    touch_active_session,
)


def register_middleware(app):
    """Register request/response middleware in security-sensitive order."""
    app.before_request(record_request_start_time(app))
    app.before_request(log_request_info(app))
    app.before_request(enforce_csrf_origin_check(app))
    app.before_request(ensure_default_language(app))
    app.before_request(ensure_pracownik_mapping(app))
    app.before_request(enforce_session_timeout(app))
    app.before_request(track_active_session(app))
    app.after_request(log_slow_requests(app))
    app.after_request(add_cache_headers(app))
    app.after_request(add_security_headers(app))


def log_request_info(app):
    if os.environ.get('ENABLE_REQUEST_LOGGING', 'false').lower() != 'true':
        return lambda: None

    def middleware():
        try:
            path = request.path or ''
            if path.startswith('/static/') or path == '/favicon.ico' or path.startswith('/.well-known'):
                return None
            full_path = getattr(request, 'full_path', None) or path
            app.logger.debug('Incoming request: %s %s', request.method, full_path)
        except Exception:
            pass
        return None

    return middleware


def _csrf_error(app, message, *, log_message=None):
    if log_message:
        app.logger.warning(log_message)
    try:
        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.is_json
            or request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
        )
    except Exception:
        wants_json = False
    if wants_json:
        return jsonify({'success': False, 'error': message}), 403
    return render_template(
        'errors/403.html',
        page_url=request.path,
        user_role=session.get('rola', ''),
    ), 403


def enforce_csrf_origin_check(app):
    """Protect state-changing browser requests using origin verification.

    Session-authenticated mutating requests fail closed when Origin/Referer is
    absent.  Cross-origin requests are rejected regardless of response type.
    Internal headless print rendering may bypass the check only with a valid,
    short-lived HMAC in ``X-Internal-Print-Token``; URL tokens are not accepted.
    """

    def middleware():
        if app.config.get('TESTING') or app.testing or 'PYTEST_CURRENT_TEST' in os.environ:
            return None
        if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return None

        internal_token = str(request.headers.get('X-Internal-Print-Token') or '').strip()
        if internal_token:
            from app.utils.security_tokens import verify_internal_print_token
            if verify_internal_print_token(request.path, internal_token):
                return None
            return _csrf_error(
                app,
                'Forbidden: invalid internal request token.',
                log_message=f'[CSRF_BLOCKED] Invalid internal print token for {request.path}',
            )

        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        source = origin or referer

        if not source:
            if session.get('login') or session.get('user_id') or session.get('zalogowany'):
                return _csrf_error(
                    app,
                    'Forbidden: Missing origin verification headers.',
                    log_message=(
                        f'[CSRF_BLOCKED] Missing Origin/Referer on authenticated '
                        f'{request.method} {request.path}'
                    ),
                )
            return None

        try:
            parsed = urlparse(source)
            source_netloc = (parsed.netloc or '').lower()
            expected_host = (request.host or '').lower()
            if not source_netloc or not expected_host or source_netloc != expected_host:
                return _csrf_error(
                    app,
                    'Forbidden: Cross-origin request blocked.',
                    log_message=(
                        f'[CSRF_BLOCKED] Cross-origin source={source_netloc!r} '
                        f'host={expected_host!r} path={request.path}'
                    ),
                )
        except Exception as exc:
            app.logger.error('[CSRF_ERROR] Invalid Origin/Referer: %s', exc)
            return _csrf_error(app, 'Forbidden: Invalid request origin.')
        return None

    return middleware


def record_request_start_time(app):
    if os.environ.get('ENABLE_SLOW_REQUEST_LOGGING', 'false').lower() != 'true':
        return lambda: None

    from flask import g

    def middleware():
        g._request_start_time = time.time()
        return None

    return middleware


def log_slow_requests(app):
    if os.environ.get('ENABLE_SLOW_REQUEST_LOGGING', 'false').lower() != 'true':
        return lambda response: response

    from flask import g

    def middleware(response):
        try:
            started = getattr(g, '_request_start_time', None)
            if started:
                duration = time.time() - started
                if duration > 15.0:
                    app.logger.warning(
                        'SLOW REQUEST: %s %s took %.2fs (User: %s)',
                        request.method,
                        request.path,
                        duration,
                        session.get('login', 'anonymous'),
                    )
        except Exception:
            pass
        return response

    return middleware


def add_cache_headers(app):
    def middleware(response):
        try:
            path = request.path or ''
            if path.startswith('/static/') or path == '/favicon.ico' or path.startswith('/.well-known'):
                response.headers['Cache-Control'] = 'public, max-age=86400'
            else:
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
        except Exception:
            pass
        return response

    return middleware


def add_security_headers(app):
    def middleware(response):
        try:
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.socket.io https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "connect-src 'self' wss: https:; "
                "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
            )
            if request.is_secure or current_app.config.get('PREFERRED_URL_SCHEME') == 'https':
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        except Exception:
            pass
        return response

    return middleware


def ensure_pracownik_mapping(app):
    """Populate missing user/employee IDs for a logged-in account."""

    def middleware():
        if not session.get('zalogowany') or not session.get('login'):
            return None
        if 'pracownik_id' in session and session.get('user_id') is not None:
            return None

        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, pracownik_id FROM uzytkownicy WHERE login = %s LIMIT 1',
                (session.get('login'),),
            )
            row = cursor.fetchone()
            if row:
                session['user_id'] = int(row[0]) if row[0] is not None else None
                session['pracownik_id'] = int(row[1]) if row[1] is not None else None
                return None

            # Best-effort legacy employee mapping; all token values remain SQL parameters.
            login = str(session.get('login') or '').lower()
            login_alpha = re.sub(r'[^a-ząćęłńóśżź ]+', ' ', login)
            tokens = [token.strip() for token in re.split(r'\s+|[_\.\-]', login_alpha) if token.strip()]
            if not tokens:
                return None
            where = ' AND '.join('LOWER(imie_nazwisko) LIKE %s' for _ in tokens)
            cursor.execute(
                f'SELECT id FROM pracownicy WHERE {where} LIMIT 2',
                tuple(f'%{token}%' for token in tokens),
            )
            rows = cursor.fetchall()
            if len(rows) == 1:
                employee_id = int(rows[0][0])
                cursor.execute(
                    'UPDATE uzytkownicy SET pracownik_id = %s WHERE login = %s',
                    (employee_id, session.get('login')),
                )
                conn.commit()
                session['pracownik_id'] = employee_id
        except Exception:
            app.logger.exception('Error ensuring pracownik mapping')
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
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

    return middleware


def ensure_default_language(app):
    def middleware():
        if session.get('app_language') is None:
            session['app_language'] = 'pl'
        return None

    return middleware


def track_active_session(app):
    """Persist online presence and enforce DB-backed session invalidation."""

    def middleware():
        if not session.get('zalogowany') or not session.get('user_id') or not session.get('login'):
            return None
        try:
            session['session_tracking_id'] = ensure_session_tracking_id(
                session.get('session_tracking_id')
            )
            now_ts = time.time()
            last_active_check = float(session.get('last_session_active_check') or 0)

            if now_ts - last_active_check >= 15:
                active = is_session_active(session.get('session_tracking_id'))
                session['last_session_active_check'] = now_ts
                session['session_active_cached'] = active
            else:
                active = bool(session.get('session_active_cached', True))

            if not active:
                app.logger.info(
                    'Session %s was deactivated; logging out %s.',
                    session.get('session_tracking_id'),
                    session.get('login'),
                )
                session.clear()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({'success': False, 'error': 'unauthenticated'}), 401
                return redirect(url_for('auth.login', timeout=1))

            last_cleanup = float(getattr(app, '_last_session_cleanup', 0))
            if now_ts - last_cleanup > 3600:
                setattr(app, '_last_session_cleanup', now_ts)
                try:
                    from app.repositories.session_repository import cleanup_abandoned_sessions
                    cleanup_abandoned_sessions(max_inactive_hours=24)
                except Exception:
                    app.logger.exception('Session cleanup failed')

            last_ping = float(session.get('last_presence_ping') or 0)
            if now_ts - last_ping >= 20:
                touch_active_session(
                    session_id=session.get('session_tracking_id'),
                    user_id=session.get('user_id'),
                    login=session.get('login'),
                    role=session.get('rola'),
                    pracownik_id=session.get('pracownik_id'),
                    display_name=session.get('imie_nazwisko') or session.get('login'),
                    last_path=request.path,
                    ip_address=request.remote_addr,
                )
                session['last_presence_ping'] = now_ts
        except Exception:
            app.logger.exception('Failed to update active session heartbeat')
        return None

    return middleware


def enforce_session_timeout(app):
    """Log out sessions that exceed the configured inactivity timeout."""

    def middleware():
        if not session.get('zalogowany'):
            return None
        try:
            timeout_minutes = int(app.config.get('SESSION_TIMEOUT_MINUTES', 720))
            now_ts = time.time()
            last_activity = float(session.get('last_activity') or 0)
            if last_activity == 0:
                session['last_activity'] = now_ts
                return None

            idle_seconds = now_ts - last_activity
            if idle_seconds > timeout_minutes * 60:
                current_app.logger.info(
                    'Session timeout: logging out %s after %s seconds idle (limit: %d min)',
                    session.get('login'),
                    int(idle_seconds),
                    timeout_minutes,
                )
                try:
                    deactivate_active_session(session.get('session_tracking_id'))
                except Exception:
                    app.logger.exception('Failed to deactivate timed-out session')
                session.clear()
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({'success': False, 'error': 'unauthenticated', 'timeout': True}), 401
                return redirect(url_for('auth.login', timeout=1))

            session['last_activity'] = now_ts
        except Exception:
            app.logger.exception('Error enforcing session timeout')
        return None

    return middleware
