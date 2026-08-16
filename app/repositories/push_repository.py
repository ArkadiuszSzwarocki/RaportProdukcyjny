"""
Automatycznie wydzielone push_repository.
"""
import mysql.connector
from app.config import DB_CONFIG, BUFOR_LOOKBACK_DAYS, BUFOR_LOOKAHEAD_DAYS
import os
from werkzeug.security import generate_password_hash
import time
import threading
from datetime import date, timedelta
import uuid
from app.db_tables import resolve_table_name
from app.core.database import get_db_connection, get_table_name

def save_push_subscription(user_id: int, login: str, rola: str, endpoint: str, p256dh: str, auth: str) -> bool:
    """Zapisz lub zaktualizuj subskrypcję Web Push dla użytkownika.

    Args:
        user_id: ID użytkownika
        login: Login użytkownika
        rola: Rola użytkownika
        endpoint: URL endpointu push (unikalny per urządzenie)
        p256dh: Klucz publiczny szyfrowania (base64)
        auth: Sekret autoryzacji (base64)

    Returns:
        True jeśli operacja się powiodła
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO push_subskrypcje (user_id, login, rola, endpoint, p256dh, auth, last_used, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), 1)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                login   = VALUES(login),
                rola    = VALUES(rola),
                p256dh  = VALUES(p256dh),
                auth    = VALUES(auth),
                last_used = NOW(),
                is_active = 1
            """,
            (user_id, login, rola, endpoint, p256dh, auth)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] save_push_subscription error: %s", e)
        return False

def delete_push_subscription(endpoint: str) -> bool:
    """Usuń subskrypcję push po jej endpointcie (np. gdy urządzenie ją odwołało).

    Args:
        endpoint: URL endpointu push do usunięcia

    Returns:
        True jeśli usunięto
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM push_subskrypcje WHERE endpoint = %s", (endpoint,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] delete_push_subscription error: %s", e)
        return False

def get_push_subscriptions_for_role(rola: str) -> list:
    """Pobierz aktywne subskrypcje push dla danej roli.

    Args:
        rola: Nazwa roli (np. 'planista', 'admin')

    Returns:
        Lista słowników z polami: id, user_id, login, endpoint, p256dh, auth
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            "WHERE rola = %s AND is_active = 1",
            (rola,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows or []
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_role error: %s", e)
        return []

def get_push_subscriptions_for_roles(roles: list) -> list:
    """Pobierz aktywne subskrypcje push dla listy ról (bez duplikatów urządzeń).

    Args:
        roles: Lista nazw ról

    Returns:
        Lista unikalnych subskrypcji (po endpoint) dla podanych ról
    """
    if not roles:
        return []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(roles))
        cursor.execute(
            f"SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            f"WHERE rola IN ({placeholders}) AND is_active = 1",
            tuple(roles)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        # Deduplicate by endpoint
        seen = set()
        result = []
        for row in (rows or []):
            ep = row['endpoint']
            if ep not in seen:
                seen.add(ep)
                result.append(row)
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_roles error: %s", e)
        return []

def get_push_subscriptions_for_login(login: str) -> list:
    """Pobierz aktywne subskrypcje push dla konkretnego loginu.

    Args:
        login: Login użytkownika

    Returns:
        Lista subskrypcji dla danego loginu
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            "WHERE login = %s AND is_active = 1",
            (login,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows or []
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_login error: %s", e)
        return []

