#!/usr/bin/env python3
"""Inspect specific plans by id or by date for debugging queue logic."""
import sys
try:
    from app.db import get_db_connection
except Exception as e:
    print('ERROR importing app.db:', e)
    sys.exit(2)
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--ids', nargs='*', type=int, help='List of plan ids to inspect')
parser.add_argument('--date', help='Date to list zakonczone on Zasyp (YYYY-MM-DD)')
args = parser.parse_args()

conn = get_db_connection()
cur = conn.cursor()
if args.ids:
    q = "SELECT id, produkt, sekcja, status, data_planu, real_start, real_stop FROM plan_produkcji WHERE id IN (%s)"
    # build placeholder string
    ph = ','.join(['%s'] * len(args.ids))
    q = q % ph
    cur.execute(q, tuple(args.ids))
    rows = cur.fetchall()
    for r in rows:
        print(r)

if args.date:
    cur.execute("SELECT id, produkt, sekcja, status, data_planu, real_start, real_stop FROM plan_produkcji WHERE sekcja='Zasyp' AND DATE(data_planu)=%s ORDER BY real_stop ASC", (args.date,))
    rows = cur.fetchall()
    print('\nZasyp closed orders on', args.date)
    for r in rows:
        print(r)

conn.close()
