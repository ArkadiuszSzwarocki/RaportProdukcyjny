"""
Automatycznie wydzielone notification_repository.
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

def get_plan_notification_context(plan_id, conn=None, cursor=None, linia='PSD'):
    """Return minimal plan context used to build notification content."""
    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor(dictionary=True)
        local_cursor.execute(
            f"""
            SELECT id, produkt, sekcja, data_planu, COALESCE(typ_produkcji, '') AS typ_produkcji,
                   COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia
            FROM {table_plan}
            WHERE id = %s
            """,
            (plan_id,)
        )
        return local_cursor.fetchone()
    except Exception:
        return None
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

def create_notifications(typ, tytul, tresc, recipient_roles, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Create one notification row for each recipient role."""
    if not recipient_roles:
        return []

    if isinstance(recipient_roles, str):
        recipient_roles = [recipient_roles]

    normalized_roles = []
    for role in recipient_roles:
        role_value = str(role or '').strip().lower()
        if role_value and role_value not in normalized_roles:
            normalized_roles.append(role_value)

    if not normalized_roles:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    created_ids = []

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        for role in normalized_roles:
            local_cursor.execute(
                """
                INSERT INTO powiadomienia
                    (typ, tytul, tresc, odbiorca_rola, odbiorca_login, link_url, plan_id, created_by_user_id)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
                """,
                (typ, tytul, tresc, role, link_url, plan_id, created_by_user_id)
            )
            try:
                created_ids.append(local_cursor.lastrowid)
            except Exception:
                pass

        if own_conn:
            local_conn.commit()

        # Wyślij Web Push do subskrybowanych urządzeń dla każdej roli (w tle, nieblokująco)
        try:
            from app.services.push_service import send_push_to_roles
            _push_url = link_url or '/'
            import threading
            threading.Thread(
                target=send_push_to_roles,
                args=(normalized_roles, tytul, tresc, _push_url),
                daemon=True
            ).start()
        except Exception:
            pass  # Push jest opcjonalny — błąd nie blokuje zapisu powiadomień

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

def create_notification_for_login(typ, tytul, tresc, recipient_login, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Create a notification targeted to a single user login."""
    login_value = str(recipient_login or '').strip()
    if not login_value:
        return None

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        local_cursor.execute(
            """
            INSERT INTO powiadomienia
                (typ, tytul, tresc, odbiorca_rola, odbiorca_login, link_url, plan_id, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (typ, tytul, tresc, '__login__', login_value, link_url, plan_id, created_by_user_id),
        )

        inserted_id = None
        try:
            inserted_id = local_cursor.lastrowid
        except Exception:
            inserted_id = None

        if own_conn:
            local_conn.commit()

        # Wyślij Web Push do urządzeń konkretnego użytkownika (w tle)
        try:
            from app.services.push_service import send_push_to_login
            _push_url = link_url or '/'
            import threading
            threading.Thread(
                target=send_push_to_login,
                args=(login_value, tytul, tresc, _push_url),
                daemon=True
            ).start()
        except Exception:
            pass  # Push jest opcjonalny

        return inserted_id
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

def list_unread_notifications(user_id, role, login=None, limit=20, linia='PSD'):
    """Return unread notifications for a single user and role."""
    if not user_id or not role:
        return []

    safe_limit = max(1, min(int(limit or 20), 100))
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT p.id, p.typ, p.tytul, p.tresc, p.link_url, p.plan_id, p.created_at, p.odbiorca_rola
            FROM powiadomienia p
            LEFT JOIN powiadomienia_odczyty po
                ON po.notification_id = p.id AND po.user_id = %s
            WHERE p.is_active = 1
              AND (
                    p.odbiorca_rola = %s
                    OR (p.odbiorca_login IS NOT NULL AND LOWER(p.odbiorca_login) = LOWER(%s))
                  )
              AND po.notification_id IS NULL
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s
            """,
            (user_id, str(role).strip().lower(), str(login or '').strip(), safe_limit)
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

def mark_notification_read(notification_id, user_id, role=None, login=None, linia='PSD'):
    """Mark a single notification as read for the given user."""
    if not notification_id or not user_id:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM powiadomienia
            WHERE id = %s
              AND is_active = 1
              AND (
                    odbiorca_rola = %s
                    OR (odbiorca_login IS NOT NULL AND LOWER(odbiorca_login) = LOWER(%s))
                  )
            LIMIT 1
            """,
            (notification_id, str(role or '').strip().lower(), str(login or '').strip()),
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return False

        cursor.execute(
            """
            INSERT IGNORE INTO powiadomienia_odczyty (notification_id, user_id)
            VALUES (%s, %s)
            """,
            (notification_id, user_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False

def mark_all_notifications_read(user_id, role, login=None, linia='PSD'):
    """Mark all unread notifications for a role as read for the given user."""
    if not user_id or not role:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT IGNORE INTO powiadomienia_odczyty (notification_id, user_id)
            SELECT p.id, %s
            FROM powiadomienia p
            LEFT JOIN powiadomienia_odczyty po
                ON po.notification_id = p.id AND po.user_id = %s
            WHERE p.is_active = 1
              AND (
                    p.odbiorca_rola = %s
                    OR (p.odbiorca_login IS NOT NULL AND LOWER(p.odbiorca_login) = LOWER(%s))
                  )
              AND po.notification_id IS NULL
            """,
            (user_id, user_id, str(role).strip().lower(), str(login or '').strip())
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False

def replace_active_notifications(typ, recipient_roles, tytul, tresc, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Replace active notifications of a given type/plan for the provided roles."""
    if not recipient_roles:
        return []

    if isinstance(recipient_roles, str):
        recipient_roles = [recipient_roles]

    normalized_roles = []
    for role in recipient_roles:
        role_value = str(role or '').strip().lower()
        if role_value and role_value not in normalized_roles:
            normalized_roles.append(role_value)

    if not normalized_roles:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        placeholders = ','.join(['%s'] * len(normalized_roles))
        query = (
            "UPDATE powiadomienia SET is_active = 0 "
            "WHERE is_active = 1 AND typ = %s AND odbiorca_rola IN (" + placeholders + ")"
        )
        params = [typ] + normalized_roles
        if plan_id is None:
            query += " AND plan_id IS NULL"
        else:
            query += " AND plan_id = %s"
            params.append(plan_id)

        local_cursor.execute(query, tuple(params))
        created_ids = create_notifications(
            typ=typ,
            tytul=tytul,
            tresc=tresc,
            recipient_roles=normalized_roles,
            link_url=link_url,
            plan_id=plan_id,
            created_by_user_id=created_by_user_id,
            conn=local_conn,
            cursor=local_cursor,
        )

        if own_conn:
            local_conn.commit()

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

def deactivate_notifications(typ, recipient_roles=None, plan_id=None, conn=None, cursor=None):
    """Deactivate active notifications matching provided filters."""
    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        query = "UPDATE powiadomienia SET is_active = 0 WHERE is_active = 1 AND typ = %s"
        params = [typ]

        if recipient_roles:
            if isinstance(recipient_roles, str):
                recipient_roles = [recipient_roles]
            normalized_roles = [str(role or '').strip().lower() for role in recipient_roles if str(role or '').strip()]
            if normalized_roles:
                placeholders = ','.join(['%s'] * len(normalized_roles))
                query += " AND odbiorca_rola IN (" + placeholders + ")"
                params.extend(normalized_roles)

        if plan_id is None:
            query += " AND plan_id IS NULL"
        else:
            query += " AND plan_id = %s"
            params.append(plan_id)

        local_cursor.execute(query, tuple(params))
        if own_conn:
            local_conn.commit()
        return True
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

def sync_dosypka_notifications(plan_id, author_name=None, created_by_user_id=None, conn=None, cursor=None, linia='PSD'):
    """Keep dosypka notifications aligned with current unconfirmed rows for a plan."""
    if not plan_id:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    recipient_roles = ('operator', 'pracownik', 'produkcja', 'lider', 'laborant', 'admin', 'zarzad', 'masteradmin')

    table_plan = get_table_name('plan_produkcji', linia)
    table_dosypki = get_table_name('dosypki', linia)

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor(dictionary=True)

        local_cursor.execute(
            f"""
            SELECT id, produkt, data_planu
            FROM {table_plan}
            WHERE id = %s
            """,
            (plan_id,)
        )
        plan_context = local_cursor.fetchone()
        if not plan_context:
            deactivate_notifications('dosypka', recipient_roles=recipient_roles, plan_id=plan_id, conn=local_conn, cursor=local_cursor)
            if own_conn:
                local_conn.commit()
            return []

        local_cursor.execute(
            f"""
            SELECT nazwa, kg
            FROM {table_dosypki}
            WHERE plan_id = %s AND potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
            ORDER BY data_zlecenia ASC, id ASC
            """,
            (plan_id,)
        )
        pending_rows = local_cursor.fetchall()

        if not pending_rows:
            deactivate_notifications('dosypka', recipient_roles=recipient_roles, plan_id=plan_id, conn=local_conn, cursor=local_cursor)
            if own_conn:
                local_conn.commit()
            return []

        # ... (rest of function unchanged, but using table-specific data)
        produkt = plan_context.get('produkt') or 'Zasyp'
        data_planu = plan_context.get('data_planu')
        author_display = str(author_name or '').strip() or 'Użytkownik'
        total_kg = sum(float(row.get('kg') or 0) for row in pending_rows)
        pending_count = len(pending_rows)
        only_no_dosypka = pending_count == 1 and str((pending_rows[0].get('nazwa') or '')).strip().lower() == 'brak dosypki'

        if only_no_dosypka:
            tytul = f'Brak dosypki: {produkt}'
            tresc = f'{author_display} oznaczył brak dosypki dla {produkt}.'
        elif pending_count == 1:
            tytul = f'Nowa dosypka: {produkt}'
            tresc = f'{author_display} dodał dosypkę {total_kg:.1f} kg dla {produkt}.'
        else:
            tytul = f'Dosypki oczekujące: {produkt}'
            tresc = f'{author_display} dodał {pending_count} pozycji dosypki, razem {total_kg:.1f} kg, dla {produkt}.'

        link_url = f'/?sekcja=Zasyp&data={data_planu}&linia={linia}' if data_planu else f'/?sekcja=Zasyp&linia={linia}'
        created_ids = replace_active_notifications(
            typ='dosypka',
            recipient_roles=recipient_roles,
            tytul=tytul,
            tresc=tresc,
            link_url=link_url,
            plan_id=plan_id,
            created_by_user_id=created_by_user_id,
            conn=local_conn,
            cursor=local_cursor,
        )

        if own_conn:
            local_conn.commit()

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass

