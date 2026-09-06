"""
Automatycznie wydzielone session_repository.
"""
import mysql.connector
from app.config import DB_CONFIG, BUFOR_LOOKBACK_DAYS, BUFOR_LOOKAHEAD_DAYS
import os
from werkzeug.security import generate_password_hash
import time
import threading
from datetime import date, timedelta, datetime
import uuid
from app.db_tables import resolve_table_name
from app.core.database import get_db_connection, get_table_name

def ensure_session_tracking_id(current_session_id=None):
    """Return a stable session tracking id."""
    value = str(current_session_id or '').strip()
    if value:
        return value
    return uuid.uuid4().hex

def touch_active_session(session_id, user_id, login, role, pracownik_id=None, display_name=None, last_path=None, ip_address=None, conn=None):
    """Upsert active session heartbeat for online users view."""
    if not session_id or not user_id or not login:
        return False

    own_conn = False
    local_conn = conn
    cursor = None
    try:
        if local_conn is None:
            local_conn = get_db_connection()
            own_conn = True
        cursor = local_conn.cursor()
        cursor.execute(
            """
            INSERT INTO aktywne_sesje (
                session_id, user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), 1)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                login = VALUES(login),
                rola = VALUES(rola),
                pracownik_id = VALUES(pracownik_id),
                display_name = VALUES(display_name),
                ip_address = VALUES(ip_address),
                last_path = VALUES(last_path),
                last_seen = NOW(),
                is_active = 1
            """,
            (session_id, user_id, login, str(role or '').lower(), pracownik_id, display_name, ip_address, last_path)
        )
        if own_conn:
            local_conn.commit()
        cursor.close()
        if own_conn:
            local_conn.close()
        return True
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
            try:
                local_conn.close()
            except Exception:
                pass
        return False

def deactivate_active_session(session_id):
    """Mark a session as logged out."""
    if not session_id:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE session_id = %s",
            (session_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            if conn:
                conn.rollback()
                conn.close()
        except Exception:
            pass
        return False


def deactivate_all_user_sessions(user_id, except_session_id=None):
    """Deactivate all active sessions for a given user ID, optionally preserving one session."""
    if not user_id:
        return False
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if except_session_id:
            cursor.execute(
                "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE user_id = %s AND session_id != %s",
                (user_id, except_session_id)
            )
        else:
            cursor.execute(
                "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE user_id = %s",
                (user_id,)
            )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            if conn:
                conn.rollback()
                conn.close()
        except Exception:
            pass
        return False

def list_online_users(active_within_minutes=30):
    """Return recent or active sessions for online users view."""
    minutes = max(1, min(int(active_within_minutes or 30), 240))
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT session_id, user_id, login, rola, pracownik_id, display_name, last_path, logged_in_at, last_seen,
                     ip_address, is_active,
                   TIMESTAMPDIFF(SECOND, last_seen, NOW()) AS idle_seconds
            FROM aktywne_sesje
            WHERE last_seen >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
            ORDER BY is_active DESC, last_seen DESC, login ASC
            """,
            (minutes,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []

def deactivate_all_user_sessions(user_id):
    """Mark all active sessions of a user as logged out in the database."""
    if not user_id:
        return False
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE user_id = %s",
            (user_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return False

def get_all_active_sessions_for_user(user_id):
    """Return all active sessions for a user, sorted by logged_in_at ASC."""
    if not user_id:
        return []
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT session_id, logged_in_at, ip_address, display_name 
            FROM aktywne_sesje 
            WHERE user_id = %s AND is_active = 1
            ORDER BY logged_in_at ASC
            """,
            (user_id,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return []

def deactivate_other_user_sessions(user_id, exclude_session_id):
    """Mark all active sessions of a user as logged out, EXCEPT the specified one."""
    if not user_id or not exclude_session_id:
        return False
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE user_id = %s AND session_id != %s",
            (user_id, exclude_session_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return False

def cleanup_abandoned_sessions(max_inactive_hours=24):
    """Mark abandoned sessions (inactive for more than max_inactive_hours) as inactive."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE aktywne_sesje 
            SET is_active = 0 
            WHERE is_active = 1 
              AND last_seen < DATE_SUB(NOW(), INTERVAL %s HOUR)
            """,
            (max_inactive_hours,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        return False


def is_session_active(session_id):
    """Check if the session tracking ID and associated user account are still active in the database."""
    if not session_id:
        return False
    
    from flask import session, request
    from datetime import datetime
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.is_active, COALESCE(u.is_active, 1)
            FROM aktywne_sesje a
            LEFT JOIN uzytkownicy u ON a.user_id = u.id
            WHERE a.session_id = %s
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        
        # If the session exists in DB, respect its active status and user account status
        if row is not None:
            is_act, is_user_act = row[0], row[1]
            cursor.close()
            conn.close()
            return bool(is_act == 1 and is_user_act == 1)
            
        # If the session does NOT exist in DB, but the Flask session cookie claims
        # we are logged in, we automatically replicate/reconstruct the session context!
        # This prevents database switches or purges from logging the user out.
        if session.get('zalogowany') and session.get('user_id'):
            u_id = session.get('user_id')
            u_login = session.get('login')
            u_rola = session.get('rola') or ''
            u_prac = session.get('pracownik_id')
            u_name = session.get('imie_nazwisko') or u_login
            u_grupa = session.get('grupa')
            
            # 1. Ensure the employee exists
            if u_prac:
                cursor.execute("SELECT id FROM pracownicy WHERE id = %s", (u_prac,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO pracownicy (id, imie_nazwisko) VALUES (%s, %s)",
                        (u_prac, u_name)
                    )
            
            # 2. Ensure the user exists
            cursor.execute("SELECT id FROM uzytkownicy WHERE id = %s", (u_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO uzytkownicy (id, login, haslo, rola, pracownik_id, grupa) VALUES (%s, %s, %s, %s, %s, %s)",
                    (u_id, u_login, 'replicated_dummy_hash', u_rola, u_prac, u_grupa)
                )
                
            # 3. Create the active session
            forwarded_for = request.headers.get('X-Forwarded-For', '')
            client_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr)
            cursor.execute("""
                INSERT INTO aktywne_sesje 
                (session_id, user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, (
                session_id,
                u_id,
                u_login,
                u_rola,
                u_prac,
                u_name,
                client_ip,
                request.path,
                datetime.now(),
                datetime.now()
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        cursor.close()
        conn.close()
        return False
    except Exception as e:
        print(f"[WARN] Failed auto-replicating session context in is_session_active: {e}")
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return True  # Fallback to True on DB error to prevent blocking users

