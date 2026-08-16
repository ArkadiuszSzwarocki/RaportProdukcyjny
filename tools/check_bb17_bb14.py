#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza wszystkie ruchy na BB17 i BB14."""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name

conn = get_db_connection()
try:
    cur = conn.cursor(dictionary=True)
    table = get_table_name('magazyn_ruch', 'Agro')
    
    dzis = date.today()
    
    print(f"\n{'='*80}")
    print(f"RUCHY NA BB01 i BB15 - {dzis}")
    print(f"{'='*80}\n")
    
    # Sprawdź BB01
    print("🔍 Szukam BB01...")
    cur.execute(
        f"SELECT id, typ_ruchu, zbiornik, ilosc, status, autor_login, autor_data "
        f"FROM {table} "
        f"WHERE (UPPER(zbiornik) LIKE '%BB01%' OR UPPER(zbiornik) LIKE '%BB_01%' OR UPPER(zbiornik) = 'BB1') "
        f"ORDER BY autor_data DESC LIMIT 20"
    )
    bb01 = cur.fetchall()
    
    if bb01:
        print(f"  Znaleziono {len(bb01)} ruchów dla BB01:\n")
        for r in bb01:
            dzis_flag = '📅 DZISIAJ' if r['autor_data'].date() == dzis else ''
            print(f"    ID: {r['id']} | typ: {r['typ_ruchu']:20s} | zbiornik: \"{r['zbiornik']}\" | ilość: {r['ilosc']:8.1f} kg | status: {r['status']:15s} | {r['autor_data']} {dzis_flag}")
    else:
        print("  ❌ Brak ruchów dla BB01\n")
    
    # Sprawdź BB15
    print("\n🔍 Szukam BB15...")
    cur.execute(
        f"SELECT id, typ_ruchu, zbiornik, ilosc, status, autor_login, autor_data "
        f"FROM {table} "
        f"WHERE (UPPER(zbiornik) LIKE '%BB15%' OR UPPER(zbiornik) LIKE '%BB_15%') "
        f"ORDER BY autor_data DESC LIMIT 20"
    )
    bb15 = cur.fetchall()
    
    if bb15:
        print(f"  Znaleziono {len(bb15)} ruchów dla BB15:\n")
        for r in bb15:
            dzis_flag = '📅 DZISIAJ' if r['autor_data'].date() == dzis else ''
            print(f"    ID: {r['id']} | typ: {r['typ_ruchu']:20s} | zbiornik: \"{r['zbiornik']}\" | ilość: {r['ilosc']:8.1f} kg | status: {r['status']:15s} | {r['autor_data']} {dzis_flag}")
    else:
        print("  ❌ Brak ruchów dla BB15\n")
    
    # Sprawdź WSZYSTKIE dzisiejsze ruchy typu PRODUKCJA (nawet bez zbiornika)
    print(f"\n{'='*80}")
    print("WSZYSTKIE DZISIEJSZE POBRANIA NA PRODUKCJĘ:")
    print(f"{'='*80}\n")
    
    cur.execute(
        f"SELECT id, typ_ruchu, zbiornik, ilosc, status, autor_login, autor_data, surowiec_id "
        f"FROM {table} "
        f"WHERE DATE(autor_data) = %s AND typ_ruchu = 'PRODUKCJA' "
        f"ORDER BY autor_data DESC",
        (dzis,)
    )
    wszystkie = cur.fetchall()
    
    if wszystkie:
        print(f"Znaleziono {len(wszystkie)} pobrań:\n")
        for r in wszystkie:
            zbiornik_display = f"\"{r['zbiornik']}\"" if r['zbiornik'] else "❌ BRAK ZBIORNIKA"
            print(f"  ID: {r['id']} | zbiornik: {zbiornik_display:20s} | ilość: {r['ilosc']:8.1f} kg | status: {r['status']:15s} | {r['autor_login']} | {r['autor_data']}")
    else:
        print("❌ Brak dzisiejszych pobrań")
    
    print()
    
finally:
    conn.close()
