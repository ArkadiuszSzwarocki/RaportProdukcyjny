from datetime import date
import os
from db import get_db_connection


def create_plan(data_planu=None, sekcja='Zasyp', produkt='E2E Test Produkt', tonaz=100.0):
    """Insert a minimal plan_produkcji row for E2E tests and return the new id."""
    # Safety: only allow running this script when explicitly enabled by env
    if os.environ.get('ALLOW_TEST_SEEDS') != '1':
        raise RuntimeError('Test seeding disabled. Set ALLOW_TEST_SEEDS=1 to enable.')
    if data_planu is None:
        data_planu = date.today()
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status) VALUES (%s, %s, %s, %s, 'zaplanowane')",
            (data_planu, sekcja, produkt, tonaz),
        )
        try:
            pid = cur.lastrowid if hasattr(cur, 'lastrowid') else None
        except Exception:
            pid = None
        if not pid:
            cur.execute(
                "SELECT id FROM plan_produkcji WHERE data_planu=%s AND sekcja=%s AND produkt=%s ORDER BY id DESC LIMIT 1",
                (data_planu, sekcja, produkt),
            )
            r = cur.fetchone()
            pid = r[0] if r else None
        conn.commit()
        print(pid)
        return pid
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    create_plan()
