"""Exercise the additive pause migration against disposable local test data."""
import re
import uuid

import pytest


@pytest.mark.require_db
def test_pause_schema_upgrade_preserves_rows_and_can_run_twice():
    from app.core.database import DB_CONFIG
    from app.db import get_db_connection
    from app.core.database_setup import _ensure_zasyp_pause_columns

    assert DB_CONFIG['database'].startswith(('rp_pr17_', 'test_'))
    table = 'test_pause_upgrade_' + uuid.uuid4().hex
    assert re.fullmatch(r'test_pause_upgrade_[0-9a-f]{32}', table)
    connection = get_db_connection()
    cursor = connection.cursor()

    class MigrationCursor:
        def execute(self, statement):
            assert 'ALTER TABLE zasyp_etapy ADD COLUMN' in statement
            cursor.execute(statement.replace('zasyp_etapy', table))

    try:
        cursor.execute(f'CREATE TABLE {table} (id INT PRIMARY KEY, marker VARCHAR(30) NOT NULL)')
        cursor.execute(f'INSERT INTO {table} VALUES (1, %s)', ('preserve-existing-row',))
        connection.commit()
        _ensure_zasyp_pause_columns(MigrationCursor())
        cursor.execute(f'UPDATE {table} SET is_paused=1, pauza_start=%s, pauza_sekundy=17 WHERE id=1',
                       ('2026-10-14 10:00:00',))
        connection.commit()
        cursor.execute(f'SELECT * FROM {table} ORDER BY id')
        before = cursor.fetchall()
        _ensure_zasyp_pause_columns(MigrationCursor())
        cursor.execute(f'SELECT * FROM {table} ORDER BY id')
        assert cursor.fetchall() == before
        assert len(before) == 1 and before[0][1] == 'preserve-existing-row'
        assert before[0][-1] == 17
    finally:
        cursor.execute(f'DROP TABLE IF EXISTS {table}')
        connection.commit()
        cursor.close()
        connection.close()
