"""Middleware functions for request/response processing and session management."""

import re
from flask import request, session
from app.db import get_db_connection


def register_middleware(app):
    """Register all middleware functions with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.before_request(log_request_info(app))
    app.before_request(ensure_default_language(app))
    app.before_request(ensure_pracownik_mapping(app))
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
            # If logged but no pracownik mapping in session, attempt to read from DB
            if session.get('zalogowany') and session.get('pracownik_id') is None and session.get('login'):
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COALESCE(pracownik_id, NULL) FROM uzytkownicy WHERE login=%s", (session.get('login'),))
                r = cursor.fetchone()
                try:
                    if r and r[0] is not None:
                        session['pracownik_id'] = int(r[0])
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
