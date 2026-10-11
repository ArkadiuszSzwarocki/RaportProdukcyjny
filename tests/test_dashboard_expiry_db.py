"""Verify expiry warnings against MySQL DATE columns in strict mode."""

from datetime import date, timedelta

import pytest

from app.db import get_db_connection
from app.services.dashboard_service import DashboardService


@pytest.mark.require_db
def test_expiry_window_with_strict_date_columns(app, monkeypatch):
    today = date(2026, 10, 11)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE'")
        cursor.execute("""
            CREATE TEMPORARY TABLE dashboard_expiry_test (
                id INT PRIMARY KEY,
                nr_palety VARCHAR(50), nazwa VARCHAR(50), nr_partii VARCHAR(50),
                lokalizacja VARCHAR(50), data_produkcji DATE,
                data_przydatnosci DATE, stan_magazynowy DECIMAL(10,2)
            )
        """)
        cursor.executemany(
            "INSERT INTO dashboard_expiry_test (id, data_przydatnosci, stan_magazynowy) VALUES (%s, %s, %s)",
            [
                (1, today + timedelta(days=30), 100),
                (2, today, 100),
                (3, today - timedelta(days=1), 100),
                (4, today + timedelta(days=31), 100),
                (5, None, 100),
                (6, today, 0),
                (7, today, -1),
            ],
        )
        monkeypatch.setattr(
            'app.services.dashboard_service.get_table_name',
            lambda *_args: 'dashboard_expiry_test',
        )
        with app.app_context():
            rows = DashboardService.get_expiring_pallets(today, 'AGRO', 30, cursor)
        assert [row['id'] for row in rows] == [2, 1]
    finally:
        cursor.close()
        conn.close()
