#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza dokładną zawartość pola zbiornik w bazie."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name

conn = get_db_connection()
try:
    cur = conn.cursor(dictionary=True)
    table = get_table_name('magazyn_ruch', 'Agro')
    cur.execute(
        f"SELECT id, zbiornik, CHAR_LENGTH(zbiornik) as len, HEX(zbiornik) as hex_val, autor_data "
        f"FROM {table} "
        f"WHERE DATE(autor_data) = %s AND typ_ruchu = 'PRODUKCJA' "
        f"ORDER BY autor_data DESC",
        (date.today(),)
    )
    rows = cur.fetchall()
    
    print(f"\nDzisiejsze pobrania - dokładne wartości pola 'zbiornik':\n")
    for r in rows:
        print(f"  ID: {r['id']:3d} | zbiornik = \"{r['zbiornik']}\" | długość = {r['len']} | HEX = {r['hex_val']} | data = {r['autor_data']}")
    print()
finally:
    conn.close()
