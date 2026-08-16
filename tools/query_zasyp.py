#!/usr/bin/env python3
"""Query local DB for closed Zasyp plans and print which finished first."""
import sys
from datetime import datetime
try:
    from app.db import get_db_connection
except Exception as e:
    print('ERROR: could not import get_db_connection from app.db:', e)
    sys.exit(2)

import argparse

def build_sql(filter_date=None):
    base = (
        "SELECT id, produkt, data_planu, status, real_start, real_stop "
        "FROM plan_produkcji "
        "WHERE sekcja = 'Zasyp' AND status = 'zakonczone' "
    )
    if filter_date:
        base += "AND DATE(data_planu) = %s "
    base += "ORDER BY COALESCE(real_stop, data_planu) ASC LIMIT 20;"
    return base

def format_row(r):
    return {
        'id': r[0], 'produkt': r[1], 'data_planu': r[2], 'status': r[3],
        'real_start': r[4], 'real_stop': r[5]
    }

def main():
    conn = None
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('date', nargs='?', help='Optional date (YYYY-MM-DD) to filter data_planu')
        args = parser.parse_args()
        filter_date = args.date
        SQL = build_sql(filter_date)
        conn = get_db_connection()
        cur = conn.cursor()
        if filter_date:
            cur.execute(SQL, (filter_date,))
        else:
            cur.execute(SQL)
        rows = cur.fetchall()
        if not rows:
            print('No closed Zasyp plans found for given criteria.')
            return
        if filter_date:
            print(f'Top results for date {filter_date} (first finished first):')
        else:
            print('Top results (first finished first):')
        for i, r in enumerate(rows, 1):
            fr = format_row(r)
            print(f"{i}. id={fr['id']} produkt={fr['produkt']} data_planu={fr['data_planu']} status={fr['status']}")
            print('   real_start=', fr['real_start'], ' real_stop=', fr['real_stop'])
    except Exception as e:
        print('ERROR running query:', e)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
