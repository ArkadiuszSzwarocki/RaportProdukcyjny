"""Bounded notification creation helpers used by the compatibility DB facade."""

from concurrent.futures import ThreadPoolExecutor

from app.core.database import get_db_connection


_PUSH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='web-push')


def _normalize_roles(recipient_roles):
    if isinstance(recipient_roles, str):
        recipient_roles = [recipient_roles]
    result = []
    for role in recipient_roles or []:
        value = str(role or '').strip().lower()
        if value and value not in result:
            result.append(value)
    return result


def _queue_push_to_roles(roles, title, body, link_url):
    try:
        from app.services.push_service import send_push_to_roles
        _PUSH_EXECUTOR.submit(send_push_to_roles, roles, title, body, link_url or '/')
    except RuntimeError:
        pass


def _queue_push_to_login(login, title, body, link_url):
    try:
        from app.services.push_service import send_push_to_login
        _PUSH_EXECUTOR.submit(send_push_to_login, login, title, body, link_url or '/')
    except RuntimeError:
        pass


def create_notifications(
    typ,
    tytul,
    tresc,
    recipient_roles,
    link_url=None,
    plan_id=None,
    created_by_user_id=None,
    conn=None,
    cursor=None,
):
    """Create role notifications and queue Web Push without spawning OS threads."""
    roles = _normalize_roles(recipient_roles)
    if not roles:
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

        for role in roles:
            local_cursor.execute(
                """
                INSERT INTO powiadomienia
                    (typ, tytul, tresc, odbiorca_rola, odbiorca_login,
                     link_url, plan_id, created_by_user_id)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
                """,
                (typ, tytul, tresc, role, link_url, plan_id, created_by_user_id),
            )
            if getattr(local_cursor, 'lastrowid', None):
                created_ids.append(local_cursor.lastrowid)

        if own_conn:
            local_conn.commit()

        # Do not dispatch external side effects before a caller-owned
        # transaction has been committed. The caller may queue explicitly after
        # commit; autonomous calls can safely queue here.
        if own_conn:
            _queue_push_to_roles(roles, tytul, tresc, link_url)
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


def create_notification_for_login(
    typ,
    tytul,
    tresc,
    recipient_login,
    link_url=None,
    plan_id=None,
    created_by_user_id=None,
    conn=None,
    cursor=None,
):
    """Create a user notification and queue Web Push in the bounded pool."""
    login = str(recipient_login or '').strip()
    if not login:
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
                (typ, tytul, tresc, odbiorca_rola, odbiorca_login,
                 link_url, plan_id, created_by_user_id)
            VALUES (%s, %s, %s, '__login__', %s, %s, %s, %s)
            """,
            (typ, tytul, tresc, login, link_url, plan_id, created_by_user_id),
        )
        inserted_id = getattr(local_cursor, 'lastrowid', None)
        if own_conn:
            local_conn.commit()
            _queue_push_to_login(login, tytul, tresc, link_url)
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


def install_notification_dispatch_hardening():
    """Replace legacy helpers so internal module calls use bounded dispatch too."""
    from app.repositories import notification_repository

    notification_repository.create_notifications = create_notifications
    notification_repository.create_notification_for_login = create_notification_for_login
    return create_notifications, create_notification_for_login
