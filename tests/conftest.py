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
    """Skip tests marked with ``require_db`` when the database is not reachable."""
    is_db_available = None  # lazy-evaluated once
    skip_marker = pytest.mark.skip(reason="requires a live MySQL database (not available in this environment)")
    for item in items:
        if item.get_closest_marker("require_db"):
            if is_db_available is None:
                is_db_available = _is_db_reachable()
            if not is_db_available:
                item.add_marker(skip_marker)


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
