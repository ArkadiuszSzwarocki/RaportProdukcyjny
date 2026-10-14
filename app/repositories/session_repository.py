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
    """Deactivate all active sessions for a user, optionally preserving one session."""
    if not user_id:
        return False

    conn = None
    cursor = None
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
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
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
    """Return True only for a DB-backed active session tied to an active user.

    Session validation is deliberately fail-closed:
    - a missing tracking record is inactive;
    - a missing/deleted user is inactive;
    - an inactive user or session is inactive;
    - any database error is treated as inactive.

    The function never reconstructs users or sessions from the Flask cookie.
    """
    if not session_id:
        return False

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.is_active, u.is_active
            FROM aktywne_sesje a
            INNER JOIN uzytkownicy u ON u.id = a.user_id
            WHERE a.session_id = %s
            LIMIT 1
            """,
            (session_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return False

        is_session_enabled, is_user_enabled = row[0], row[1]
        return bool(is_session_enabled == 1 and is_user_enabled == 1)
    except Exception as error:
        # Security-sensitive validation must fail closed.  A temporary DB issue
        # can require a fresh login, but must never grant access by default.
        try:
            import logging
            logging.getLogger('app.security').warning(
                'Session validation failed closed for session %s: %s',
                str(session_id)[:12],
                error,
            )
        except Exception:
            pass
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
