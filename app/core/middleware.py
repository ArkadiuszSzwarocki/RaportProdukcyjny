"""Middleware functions for request/response processing and session management."""

import re
import time
from datetime import timedelta
from flask import request, session, redirect, current_app, url_for
from app.db import get_db_connection, ensure_session_tracking_id, touch_active_session, deactivate_active_session


def register_middleware(app):
    """Register all middleware functions with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.before_request(record_request_start_time(app))
    app.before_request(log_request_info(app))
    app.before_request(ensure_default_language(app))
    app.before_request(ensure_pracownik_mapping(app))
    app.before_request(enforce_session_timeout(app))
    app.before_request(track_active_session(app))
    app.after_request(log_slow_requests(app))
    app.after_request(add_cache_headers(app))


def log_request_info(app):
    """Middleware: Log incoming requests (except static/well-known paths).
    
    Args:
        app: Flask application instance
        
    Returns:
        Middleware function for before_request
    """
    def middleware():
        try:
            # Skip noisy static file and well-known requests from debug logs to reduce noise
            p = request.path or ''
            if p.startswith('/static/') or p == '/favicon.ico' or p.startswith('/.well-known'):
                return
            # Use full_path to include query string, helps debugging links like ?sekcja=...
            full = getattr(request, 'full_path', None) or request.path
            try:
                import os as _os
                pid = _os.getpid()
            except Exception:
                pid = 'unknown'
            app.logger.debug('Incoming request (pid=%s): %s %s', pid, request.method, full)
        except Exception:
            pass
    return middleware


def record_request_start_time(app):
    """Middleware: Monitor request start time for performance tracking."""
    from flask import g
    def middleware():
        try:
            g._request_start_time = time.time()
        except Exception:
            pass
    return middleware


def log_slow_requests(app):
    """Middleware: Log requests exceeding 2 seconds (Performance Trap)."""
    from flask import g
    def middleware(response):
        try:
            start_time = getattr(g, '_request_start_time', None)
            if start_time:
                duration = time.time() - start_time
                if duration > 2.0:
                    user = session.get('login', 'anonymous')
                    app.logger.warning('SLOW REQUEST: %s %s took %.2fs (User: %s)', request.method, request.path, duration, user)
        except Exception:
            pass
        return response
    return middleware


def add_cache_headers(app):
    """Middleware: Add caching headers for static assets and favicon.
    
    Args:
        app: Flask application instance
        
    Returns:
        Middleware function for after_request
    """
    def middleware(response):
        try:
            p = request.path or ''
            # Add caching for static assets and favicon to reduce repeated requests
            if p.startswith('/static/') or p == '/favicon.ico' or p.startswith('/.well-known'):
                # cache for 1 day
                response.headers['Cache-Control'] = 'public, max-age=86400'
        except Exception:
            pass
        return response
    return middleware


def ensure_pracownik_mapping(app):
    """Middleware: Ensure logged-in users have pracownik_id mapped in session.
    
    Attempts to:
    1. Read existing pracownik_id from uzytkownicy table
    2. Auto-map based on login if not found (searches pracownicy by tokenized name)
    3. Update database if auto-mapping succeeds
    
    Args:
        app: Flask application instance
        
    Returns:
        Middleware function for before_request
    """
    def middleware():
        try:
            # If logged but user/pracownik mapping is incomplete in session, attempt to read from DB
            if session.get('zalogowany') and session.get('login') and (session.get('pracownik_id') is None or session.get('user_id') is None):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login=%s", (session.get('login'),))
                r = cursor.fetchone()
                try:
                    if r:
                        if r[0] is not None:
                            session['user_id'] = int(r[0])
                        if r[1] is not None:
                            session['pracownik_id'] = int(r[1])
                    else:
                        # Try a best-effort automatic mapping on first login: tokenize login and search pracownicy
                        try:
                            l = session.get('login').lower()
                            l_alpha = re.sub(r"[^a-ząćęłńóśżź ]+", ' ', l)
                            tokens = [t.strip() for t in re.split(r"\s+|[_\.\-]", l_alpha) if t.strip()]
                            if tokens:
                                where_clauses = " AND ".join(["LOWER(imie_nazwisko) LIKE %s" for _ in tokens])
                                params = tuple([f"%{t}%" for t in tokens])
                                q = f"SELECT id FROM pracownicy WHERE {where_clauses} LIMIT 2"
                                cursor.execute(q, params)
                                rows = cursor.fetchall()
                                if len(rows) == 1:
                                    prac_id = int(rows[0][0])
                                    try:
                                        cursor.execute("UPDATE uzytkownicy SET pracownik_id=%s WHERE login=%s", (prac_id, session.get('login')))
                                        conn.commit()
                                        session['pracownik_id'] = prac_id
                                        try:
                                            app.logger.info('Auto-mapped login %s -> pracownik_id=%s', session.get('login'), prac_id)
                                        except Exception:
                                            pass
                                    except Exception:
                                        try:
                                            conn.rollback()
                                        except Exception:
                                            pass
                        except Exception:
                            try:
                                app.logger.exception('Error during auto-mapping attempt')
                            except Exception:
                                pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception:
            try:
                app.logger.exception('Error ensuring pracownik mapping')
            except Exception:
                pass
    return middleware


def ensure_default_language(app):
    """Middleware: Ensure `session['app_language']` defaults to Polish ('pl').

    Sets the language in session when it's not already present. This ensures
    templates and translation helper default to Polish after app start.
    """
    def middleware():
        try:
            # Only set default if not already configured in session/cookies
            if session.get('app_language') is None:
                session['app_language'] = 'pl'
        except Exception:
            try:
                app.logger.exception('Failed to set default app_language in session')
            except Exception:
                pass
    return middleware


def track_active_session(app):
    """Persist lightweight online presence for logged-in users."""
    def middleware():
        try:
            if not session.get('zalogowany') or not session.get('user_id') or not session.get('login'):
                return

            session['session_tracking_id'] = ensure_session_tracking_id(session.get('session_tracking_id'))
            now_ts = time.time()
            last_ping = float(session.get('last_presence_ping') or 0)
            if now_ts - last_ping < 20:
                return

            touch_active_session(
                session_id=session.get('session_tracking_id'),
                user_id=session.get('user_id'),
                login=session.get('login'),
                role=session.get('rola'),
                pracownik_id=session.get('pracownik_id'),
                display_name=session.get('imie_nazwisko') or session.get('login'),
                last_path=request.path,
            )
            session['last_presence_ping'] = now_ts
        except Exception:
            try:
                app.logger.exception('Failed to update active session heartbeat')
            except Exception:
                pass
    return middleware


def enforce_session_timeout(app):
    """Middleware: enforce server-side inactivity logout based on `app.config['SESSION_TIMEOUT_MINUTES']`.

    If user's last activity (stored in `session['last_activity']`) is older than the configured
    timeout, the session is cleared and the active session is deactivated in the DB.
    Returns a redirect to `/login` when timed out.
    """
    def middleware():
        try:
            timeout_min = int(app.config.get('SESSION_TIMEOUT_MINUTES', 40))
            if not session.get('zalogowany'):
                return

            now_ts = time.time()
            last_activity = float(session.get('last_activity') or 0)
            # If last_activity is missing, set it now so we don't immediately logout newly logged users
            if last_activity == 0:
                session['last_activity'] = now_ts
                return

            idle_seconds = now_ts - last_activity
            if idle_seconds > (timeout_min * 60):
                try:
                    current_app.logger.info('Session timeout: logging out %s after %s seconds idle', session.get('login'), int(idle_seconds))
                except Exception:
                    pass
                # Deactivate tracked session in DB
                try:
                    deactivate_active_session(session.get('session_tracking_id'))
                except Exception:
                    pass
                session.clear()
                # Redirect to login with a timeout flag so the login page can show a message
                return redirect(url_for('auth.login', timeout=1))

            # Otherwise refresh last_activity
            session['last_activity'] = now_ts
        except Exception:
            try:
                app.logger.exception('Error enforcing session timeout')
            except Exception:
                pass
    return middleware
