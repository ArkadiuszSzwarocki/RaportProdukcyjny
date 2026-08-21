#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fetch movement history for pallets associated with production tank WZ04.
Outputs rows from magazyn_ruch where zbiornik='WZ04'."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, surowiec_id, surowiec_nazwa, typ_ruchu, ilosc, ilosc_po,
               zbiornik, status, autor_login, autor_data, komentarz
        FROM magazyn_ruch
        WHERE zbiornik = %s
        ORDER BY autor_data DESC
        LIMIT 100
    """, ('WZ04',))
    rows = cur.fetchall()
    if not rows:
        print('No movement entries found for zbiornik WZ04')
    else:
        print(f"Found {len(rows)} movement entries for zbiornik WZ04:\n")
        for r in rows:
            print(f"ID:{r['id']} | Surowiec:{r['surowiec_nazwa']} (ID {r['surowiec_id']}) | Typ:{r['typ_ruchu']} | Ilość:{r['ilosc']} -> {r['ilosc_po']} kg | Status:{r['status']} | Data:{r['autor_data']} | Autor:{r['autor_login']} | Komentarz:{r['komentarz'] or '(brak)'}")
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
