# cspell:words calkowita CURDATE lastrowid
"""A shared bucket table must not mix PSD and AGRO plan identifiers."""
import uuid

import pytest


@pytest.mark.require_db
@pytest.mark.parametrize('line', ['PSD', 'AGRO'])
def test_cancel_addition_counts_only_buckets_from_the_same_line(line):
    from app.core.database import DB_CONFIG
    from app.db import get_db_connection, get_table_name
    from app.repositories.production_repository import cancel_confirmed_dosypka

    assert DB_CONFIG['database'].startswith(('rp_pr17_', 'test_'))
    plan_table = get_table_name('plan_produkcji', line)
    addition_table = get_table_name('dosypki', line)
    other_line = 'AGRO' if line == 'PSD' else 'PSD'
    marker = uuid.uuid4().hex
    connection = get_db_connection()
    cursor = connection.cursor()
    plan_id = None
    buckets = []
    try:
        cursor.execute(f"INSERT INTO {plan_table} (produkt, data_planu, sekcja, status, tonaz) "
                       "VALUES (%s, CURDATE(), 'Zasyp', 'w toku', 100)", ('Line isolation ' + marker,))
        plan_id = cursor.lastrowid
        cursor.execute(f'INSERT INTO {addition_table} (plan_id, nazwa, kg, potwierdzone) VALUES (%s, %s, 5, 1)',
                       (plan_id, 'Cancel ' + marker))
        addition_id = cursor.lastrowid
        for bucket_line, weight in [(line, 10), (other_line, 999)]:
            cursor.execute("INSERT INTO wiaderka_maluchy (kod_wiadra, nr_sscc, plan_id, linia, status, waga_calkowita) "
                           "VALUES (%s, %s, %s, %s, 'wrzucone_do_mieszalnika', %s)",
                           ('TEST_' + marker, marker + bucket_line, plan_id, bucket_line, weight))
            buckets.append(cursor.lastrowid)
        connection.commit()
        ok, message, returned_id = cancel_confirmed_dosypka(addition_id, 'test-supervisor', linia=line)
        assert ok, message
        assert returned_id == plan_id
        cursor.execute(f'SELECT tonaz_rzeczywisty FROM {plan_table} WHERE id=%s', (plan_id,))
        assert float(cursor.fetchone()[0]) == 10
    finally:
        for bucket_id in buckets:
            cursor.execute('DELETE FROM wiaderka_maluchy WHERE id=%s', (bucket_id,))
        if plan_id:
            cursor.execute(f'DELETE FROM {addition_table} WHERE plan_id=%s', (plan_id,))
            cursor.execute(f'DELETE FROM {plan_table} WHERE id=%s', (plan_id,))
        connection.commit()
        cursor.close()
        connection.close()
