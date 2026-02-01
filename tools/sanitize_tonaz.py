#!/usr/bin/env python3
"""Sanityzator pola `tonaz_rzeczywisty`:
- aktualizuje istniejące NULL -> 0
- opcjonalnie modyfikuje schemat (ALTER) aby kolumna miała DEFAULT 0

Użycie:
  python tools/sanitize_tonaz.py --update-only   # tylko UPDATE NULL->0
  python tools/sanitize_tonaz.py --alter         # wykona ALTER TABLE by ustawić DEFAULT 0 (bezpiecznie)
"""
import argparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection

def update_nulls():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(1) FROM plan_produkcji WHERE tonaz_rzeczywisty IS NULL")
        cnt = cur.fetchone()[0]
        print('Found NULL tonaz_rzeczywisty rows:', cnt)
        if cnt > 0:
            cur.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty = 0 WHERE tonaz_rzeczywisty IS NULL")
            conn.commit()
            print('Updated NULL -> 0')
    finally:
        try: conn.close()
        except Exception: pass

def alter_default():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        print('Attempting to ALTER TABLE plan_produkcji to set DEFAULT 0 for tonaz_rzeczywisty')
        cur.execute("ALTER TABLE plan_produkcji MODIFY COLUMN tonaz_rzeczywisty DOUBLE DEFAULT 0")
        conn.commit()
        print('ALTER TABLE executed (if permitted)')
    except Exception as e:
        print('ALTER failed or not permitted:', e)
        try: conn.rollback()
        except Exception: pass
    finally:
        try: conn.close()
        except Exception: pass

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--update-only', action='store_true')
    p.add_argument('--alter', action='store_true')
    args = p.parse_args()
    if args.update_only:
        update_nulls()
    elif args.alter:
        update_nulls()
        alter_default()
    else:
        update_nulls()
        print('Done. Use --alter to also attempt ALTER TABLE to set DEFAULT 0.')
