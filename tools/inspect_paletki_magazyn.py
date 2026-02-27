#!/usr/bin/env python3
"""Inspect get_paletki_magazyn output for a given date.
Usage: python tools/inspect_paletki_magazyn.py 2026-02-23
"""
import sys
from datetime import datetime

sys.path.insert(0, '.')

from app.utils.queries import QueryHelper


def inspect(date_str):
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception as e:
        print('Invalid date format, use YYYY-MM-DD')
        return

    rows = QueryHelper.get_paletki_magazyn(d)
    print(f"Found {len(rows)} rows for {date_str}\n")
    for i, r in enumerate(rows, start=1):
        print('--- Row', i, '---')
        # print full repr
        for idx, val in enumerate(r):
            print(f'[{idx}] = {val!r}')
        # If paleta_workowanie row: fetch original pw row for comparison when possible
        try:
            # pw.id is in r[0] for both selects; if pw exists in palety_workowanie, fetch it
            import app.db as db
            conn = db.get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT id, data_dodania, data_potwierdzenia, czas_rzeczywistego_potwierdzenia FROM palety_workowanie WHERE id = %s', (r[0],))
            pw = cur.fetchone()
            cur.close()
            conn.close()
            if pw:
                print('palety_workowanie row:', pw)
        except Exception:
            pass
        print()


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime('%Y-%m-%d')
    inspect(date_arg)
