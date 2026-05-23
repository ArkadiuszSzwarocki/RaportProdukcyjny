"""Middleware functions for request/response processing and session management."""

import re
import time
from datetime import timedelta
from flask import request, session, redirect, current_app, url_for, jsonify
from app.db import get_db_connection, ensure_session_tracking_id, touch_active_session, deactivate_active_session, is_session_active


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
    """Middleware: Add caching headers for static assets and favicon, and disable caching for dynamic routes.
    
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
            else:
                # Disable browser and intermediate caching for dynamic views to prevent BFCache session leaks
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
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
            if session.get('zalogowany') and session.get('login') and ('pracownik_id' not in session or session.get('user_id') is None):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login=%s", (session.get('login'),))
                r = cursor.fetchone()
                try:
                    if r:
                        if r[0] is not None:
                            session['user_id'] = int(r[0])
                        # Always set the key (even as None) to prevent subsequent DB hits on every request
                        session['pracownik_id'] = int(r[1]) if r[1] is not None else None
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
    """Persist lightweight online presence for logged-in users and validate session status."""
    def middleware():
        try:
            if not session.get('zalogowany') or not session.get('user_id') or not session.get('login'):
                return

            session['session_tracking_id'] = ensure_session_tracking_id(session.get('session_tracking_id'))
            
            # Check if this session has been deactivated (e.g. from logout on another device)
            # Rate-limit database active check to at most once every 15 seconds to avoid heavy DB overhead
            now_ts = time.time()
            last_active_check = float(session.get('last_session_active_check') or 0)
            is_active = True
            
            if now_ts - last_active_check >= 15:
                is_active = is_session_active(session.get('session_tracking_id'))
                session['last_session_active_check'] = now_ts
                session['session_active_cached'] = is_active
            else:
                is_active = session.get('session_active_cached', True)

            if not is_active:
                try:
                    app.logger.info("Session %s was deactivated in DB. Force logging out user %s.", 
                                    session.get('session_tracking_id'), session.get('login'))
                except Exception:
                    pass
                session.clear()
                
                try:
                    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
                except Exception:
                    is_xhr = False; accepts_json = False
                
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'unauthenticated'}), 401
                return redirect(url_for('auth.login', timeout=1))

            now_ts = time.time()
            last_ping = float(session.get('last_presence_ping') or 0)
            if now_ts - last_ping < 20:
                return

            forwarded_for = request.headers.get('X-Forwarded-For', '')
            client_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr)
            touch_active_session(
                session_id=session.get('session_tracking_id'),
                user_id=session.get('user_id'),
                login=session.get('login'),
                role=session.get('rola'),
                pracownik_id=session.get('pracownik_id'),
                display_name=session.get('imie_nazwisko') or session.get('login'),
                last_path=request.path,
                ip_address=client_ip,
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
    Returns 401 status for AJAX/JSON requests or a redirect to `/login` when timed out.
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
            # Debug log to catch "flashing" session timeout issues
            try:
                app.logger.info(f"Session check: user={session.get('login')}, role={session.get('rola')}, idle={idle_seconds:.1f}s, limit={timeout_min}m, zalogowany={session.get('zalogowany')}")
            except Exception:
                pass
            
            if idle_seconds > (timeout_min * 60):
                try:
                    current_app.logger.info('Session timeout: logging out %s after %s seconds idle (limit: %d min)', 
                                            session.get('login'), int(idle_seconds), timeout_min)
                except Exception:
                    pass
                # Deactivate tracked session in DB
                try:
                    deactivate_active_session(session.get('session_tracking_id'))
                except Exception:
                    pass
                session.clear()
                
                try:
                    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    accepts_json = request.accept_mimetypes.best_match(['application/json', 'text/html']) == 'application/json'
                except Exception:
                    is_xhr = False; accepts_json = False
                
                if is_xhr or accepts_json:
                    return jsonify({'success': False, 'error': 'unauthenticated', 'timeout': True}), 401
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
