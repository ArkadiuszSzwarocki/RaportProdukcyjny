"""Pytest configuration and fixtures for test suite."""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, date

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _is_db_reachable() -> bool:
    """Return True if the configured MySQL database is reachable."""
    try:
        import mysql.connector
        from app.config import DB_CONFIG
        conn = mysql.connector.connect(**DB_CONFIG)
        conn.close()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Skip require_db tests if MySQL DB is not reachable."""
    if not _is_db_reachable():
        skip_db = pytest.mark.skip(reason="Wymagane jest połączone środowisko bazy MySQL")
        for item in items:
            if "require_db" in item.keywords:
                item.add_marker(skip_db)


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    """Ensure database schema and test data exist when connected to real DB in CI."""
    if _is_db_reachable():
        try:
            from werkzeug.security import generate_password_hash
            from app.db import get_db_connection
            from app.core.database_setup import (
                _create_tables,
                _migrate_columns,
                _create_composite_indexes,
            )
            conn = get_db_connection()
            cursor = conn.cursor()
            _create_tables(cursor)
            _migrate_columns(cursor)
            _create_composite_indexes(cursor)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wiaderka_maluchy (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    kod_wiadra VARCHAR(50),
                    nr_sscc VARCHAR(50),
                    plan_id INT,
                    szarza_id INT,
                    status VARCHAR(50),
                    waga_calkowita DECIMAL(10,2) DEFAULT 0,
                    operator_nawazyl_login VARCHAR(100),
                    data_produkcji DATETIME,
                    data_przydatnosci DATETIME,
                    data_rozpoczecia DATETIME,
                    data_skompletowania DATETIME NULL,
                    data_zakonczenia DATETIME,
                    operator VARCHAR(100),
                    linia VARCHAR(50),
                    mieszalnik_kod VARCHAR(50),
                    data_zasypania DATETIME,
                    operator_zasypal_login VARCHAR(100)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wiaderka_maluchy_pozycje (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    wiaderko_id INT,
                    stacja_kod VARCHAR(50),
                    surowiec_nazwa VARCHAR(255),
                    waga_faktyczna DECIMAL(10,2) DEFAULT 0,
                    data_nawazenia DATETIME,
                    operator_login VARCHAR(100)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS magazyn_archiwum (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    original_id INT NULL,
                    nr_palety VARCHAR(50) NULL,
                    nazwa VARCHAR(255) NULL,
                    typ_palety VARCHAR(50) NULL,
                    linia VARCHAR(10) NULL,
                    nr_partii VARCHAR(100) NULL,
                    waga_ostatnia FLOAT NULL,
                    lokalizacja_ostatnia VARCHAR(100) NULL,
                    data_archiwizacji DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_login VARCHAR(100) NULL,
                    komentarz TEXT NULL,
                    INDEX idx_ma_nr_palety (nr_palety),
                    INDEX idx_ma_original_id (original_id)
                )
            """)

            common_surowce = [
                'Lactose', 'Laktoza', 'Serwatka', 'Cukier', 'Glukoza', 'Mleko w proszku',
                'WPC80', 'WPC35', 'Kazeina', 'Permeat'
            ]
            for s_name in common_surowce:
                cursor.execute("INSERT IGNORE INTO slownik_surowcow (nazwa) VALUES (%s)", (s_name,))

            test_users = [
                ('GontaArt', 'Artur2026', 'magazynier', 'OSIP'),
                ('admin', 'admin123', 'admin', 'ALL'),
                ('lider', 'lider123', 'lider', 'PSD'),
                ('planista', 'planista123', 'planista', 'PSD'),
                ('pracownik', 'pracownik123', 'pracownik', 'PSD'),
            ]
            for login_val, pass_val, rola_val, grupa_val in test_users:
                cursor.execute("SELECT id FROM uzytkownicy WHERE login=%s", (login_val,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)",
                        (login_val, generate_password_hash(pass_val, method='pbkdf2:sha256'), rola_val, grupa_val)
                    )

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[TEST DB SETUP WARN] {e}")



@pytest.fixture
def app():
    """Create and configure a Flask app instance for testing."""
    # Set test flag to skip database initialization
    os.environ['PYTEST_CURRENT_TEST'] = 'true'
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['SECRET_KEY'] = 'test-secret-key-123'
    
    from app.core.factory import create_app
    
    app = create_app(init_db=False)
    app.config['TESTING'] = True
    
    return app


@pytest.fixture
def client(app):
    """Create a test client for making requests to the app.

    ``get_db_connection`` is patched to return a MagicMock so that routes
    which probe the database (e.g. the health-check endpoint) behave as if a
    database is available.  Tests that want to simulate a DB failure can still
    override the patch inside their own ``with patch(...)`` block.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    with patch('app.db.get_db_connection', return_value=mock_conn):
        yield app.test_client()


@pytest.fixture
def runner(app):
    """Create a CLI test runner."""
    return app.test_cli_runner()


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


@pytest.fixture
def mock_get_db_connection(mock_db_connection):
    """Mock the get_db_connection function."""
    mock_conn, mock_cursor = mock_db_connection
    with patch('app.db.get_db_connection', return_value=mock_conn):
        yield mock_conn, mock_cursor


@pytest.fixture
def authenticated_client(client, app):
    """Create an authenticated test client with session."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'testuser'
        sess['rola'] = 'pracownik'
        sess['pracownik_id'] = 100
    return client


@pytest.fixture
def admin_client(client, app):
    """Create an admin authenticated test client."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['rola'] = 'admin'
        sess['pracownik_id'] = 1
    return client


@pytest.fixture
def lider_client(client, app):
    """Create a lider (supervisor) authenticated test client."""
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'lider'
        sess['rola'] = 'lider'
        sess['pracownik_id'] = 50
    return client


@pytest.fixture
def mock_query_helper():
    """Mock the QueryHelper class."""
    with patch('app.utils.queries.QueryHelper') as mock:
        # Mock common query methods
        mock.get_pracownicy.return_value = [
            (1, 'Adam', 'Kowalski'),
            (2, 'Beata', 'Nowak'),
            (3, 'Czesław', 'Lewandowski'),
        ]
        mock.get_obsada_zmiany.return_value = [
            (1, 'Adam', 'Kowalski', 'sekcja1'),
            (2, 'Beata', 'Nowak', 'sekcja1'),
        ]
        mock.get_dziennik_zmiany.return_value = [
            (1, 'Adam', 'sekcja1', datetime(2026, 2, 7, 6, 0), datetime(2026, 2, 7, 14, 0)),
        ]
        mock.get_paletki_magazyn.return_value = []
        mock.get_zasyp_started_produkty.return_value = []
        yield mock


@pytest.fixture
def sample_date():
    """Provide a sample date for testing."""
    return date(2026, 2, 7)


@pytest.fixture
def sample_datetime():
    """Provide a sample datetime for testing."""
    return datetime(2026, 2, 7, 10, 30, 0)
