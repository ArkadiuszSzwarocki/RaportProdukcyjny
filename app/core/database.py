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
    
    _persist_database_name(target_name)
    
    # Automatically initialize / migrate tables in the newly active database!
    try:
        from app.core.database_setup import setup_database
        setup_database()
    except Exception as e:
        print(f"[WARN] Failed to setup database {target_name} on switch: {e}")
        
    return target_name

def get_db_connection(retries=3):
    """Get database connection with retry logic"""
    last_error = None
    for attempt in range(retries):
        try:
            with _DB_CONFIG_LOCK:
                conn_config = dict(DB_CONFIG)
            return mysql.connector.connect(**conn_config, buffered=True)
        except mysql.connector.Error as e:
            last_error = e
            if attempt < retries - 1:
                # Wait before retrying (exponential backoff)
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            continue
    # If all retries failed, raise the last error
    raise last_error

def get_table_name(base_table, linia='PSD'):
    """Return table name based on production line (PSD or AGRO)."""
    return resolve_table_name(base_table, linia)

_persisted_db = _load_persisted_database_name()

