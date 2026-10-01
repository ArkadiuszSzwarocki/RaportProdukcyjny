"""
Moduł zarządzania połączeniem z bazą danych.
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

_DB_CONFIG_LOCK = threading.Lock()
_RUNTIME_SWITCHABLE_DATABASES = ('biblioteka', 'biblioteka_testowa', 'biblioteka_test')
_DB_PERSISTENCE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.active_db_name')
is_local = os.getenv('LOCAL_ENV', 'false').lower() == 'true' or os.getenv('IS_LOCAL', 'false').lower() == 'true' or os.getenv('FLASK_ENV', 'production').lower() == 'development'
_is_ci_env = str(os.getenv('CI', '')).lower() == 'true' or str(os.getenv('GITHUB_ACTIONS', '')).lower() == 'true'
_is_test_env = str(os.getenv('FLASK_ENV', '')).lower() == 'testing' or 'PYTEST_CURRENT_TEST' in os.environ


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def get_runtime_switchable_databases():
    """Return list of database names allowed for runtime switching."""
    return list(_RUNTIME_SWITCHABLE_DATABASES)


def _persist_database_name(name):
    try:
        with open(_DB_PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
            f.write(name)
    except Exception:
        pass


def _load_persisted_database_name():
    if os.path.exists(_DB_PERSISTENCE_FILE):
        try:
            with open(_DB_PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
                name = f.read().strip()
                if name in _RUNTIME_SWITCHABLE_DATABASES:
                    return name
        except Exception:
            pass
    return None


def get_active_database_name():
    """Return currently active database name from runtime config."""
    with _DB_CONFIG_LOCK:
        return str(DB_CONFIG.get('database') or '')


def set_active_database_name(database_name, verify_connection=True):
    """Switch active database used by get_db_connection.
    
    Raises:
        ValueError: when database is not allowed or empty.
        mysql.connector.Error: when test connection fails.
    """
    target_name = str(database_name or '').strip()
    if not target_name:
        raise ValueError('Nie podano nazwy bazy danych.')
    if target_name not in _RUNTIME_SWITCHABLE_DATABASES:
        raise ValueError(f'Baza {target_name} nie jest dozwolona do przełączania.')

    # Validate connectivity before mutating global runtime config.
    if verify_connection:
        with _DB_CONFIG_LOCK:
            test_config = dict(DB_CONFIG)
        test_config['database'] = target_name
        probe = mysql.connector.connect(**test_config, buffered=True)
        probe.close()

    with _DB_CONFIG_LOCK:
        DB_CONFIG['database'] = target_name

    global _DB_POOL
    with _DB_POOL_LOCK:
        _DB_POOL = None

    _persist_database_name(target_name)

    # Automatically initialize / migrate tables in the newly active database.
    try:
        from app.core.database_setup import setup_database
        setup_database()
    except Exception as e:
        print(f"[WARN] Failed to setup database {target_name} on switch: {e}")

    return target_name


_DB_POOL = None
_DB_POOL_LOCK = threading.Lock()


def _get_or_create_pool():
    """Lazily initialize or return MySQL connection pool matching current DB_CONFIG."""
    global _DB_POOL
    with _DB_POOL_LOCK:
        with _DB_CONFIG_LOCK:
            target_db = DB_CONFIG.get('database')
            target_host = DB_CONFIG.get('host')
            pool_config = dict(DB_CONFIG)

        current_pool_db = getattr(_DB_POOL, '_pool_database', None) if _DB_POOL else None
        current_pool_host = getattr(_DB_POOL, '_pool_host', None) if _DB_POOL else None

        if _DB_POOL is None or current_pool_db != target_db or current_pool_host != target_host:
            try:
                from mysql.connector import pooling
                pool = pooling.MySQLConnectionPool(
                    pool_name="app_db_pool",
                    pool_size=32,
                    pool_reset_session=True,
                    **pool_config
                )
                pool._pool_database = target_db
                pool._pool_host = target_host
                _DB_POOL = pool
            except Exception:
                _DB_POOL = None
        return _DB_POOL


def get_db_connection(retries=2):
    """Return a DB connection without silently changing the configured host.

    In production, a failure of the configured database must remain a failure;
    transparently trying localhost can connect the request to a completely
    different database.  Localhost fallback is available only in local/test
    environments or after an explicit ``DB_ALLOW_LOCALHOST_FALLBACK=true``.
    """
    try:
        pool = _get_or_create_pool()
        if pool:
            return pool.get_connection()
    except Exception:
        pass

    last_error = None
    with _DB_CONFIG_LOCK:
        base_config = dict(DB_CONFIG)

    primary_host = str(base_config.get('host') or '127.0.0.1').strip()
    candidate_hosts = [primary_host]
    allow_local_fallback = (
        is_local
        or _is_test_env
        or _env_bool('DB_ALLOW_LOCALHOST_FALLBACK', False)
    )
    if allow_local_fallback and primary_host not in ('127.0.0.1', 'localhost'):
        candidate_hosts.extend(['127.0.0.1', 'localhost'])

    num_retries = max(1, int(retries or 1))
    for host in candidate_hosts:
        conn_config = dict(base_config)
        conn_config['host'] = host
        for attempt in range(num_retries):
            try:
                return mysql.connector.connect(**conn_config, buffered=True)
            except mysql.connector.Error as exc:
                last_error = exc
                if attempt < num_retries - 1:
                    time.sleep(0.2)

    if last_error is not None:
        raise last_error
    raise RuntimeError('Nie udało się uzyskać połączenia z bazą danych.')


def get_table_name(base_table, linia='PSD'):
    """Return a validated table name based on production line."""
    return resolve_table_name(base_table, linia)


_persisted_db = _load_persisted_database_name()
if _persisted_db:
    with _DB_CONFIG_LOCK:
        DB_CONFIG['database'] = _persisted_db
