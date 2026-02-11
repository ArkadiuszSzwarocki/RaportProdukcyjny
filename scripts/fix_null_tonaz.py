import sys
import os
repo_root = os.path.dirname(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.db import get_db_connection


def find_null_tonaz():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, sekcja, produkt, DATE(data_planu), tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE tonaz IS NULL")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fix_null_tonaz():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE plan_produkcji SET tonaz = COALESCE(tonaz_rzeczywisty, 0) WHERE tonaz IS NULL")
    updated = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return updated


if __name__ == '__main__':
    rows = find_null_tonaz()
    if not rows:
        print('No plan_produkcji rows with NULL tonaz found.')
    else:
        print('Found rows with NULL tonaz:')
        for r in rows:
            print(r)
        print('\nApplying fix: setting tonaz = COALESCE(tonaz_rzeczywisty, 0) for these rows...')
        updated = fix_null_tonaz()
        print(f'Updated {updated} rows.')
        rows_after = find_null_tonaz()
        print('Remaining rows with NULL tonaz after fix:', len(rows_after))
