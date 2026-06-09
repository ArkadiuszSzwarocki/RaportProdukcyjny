#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdza magazyn_agro_ruch.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db

def check_agro_ruch():
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print("=" * 80)
    print("SPRAWDZANIE magazyn_agro_ruch")
    print("=" * 80)
    
    # Sprawdź wszystkie wpisy PRODUKCJA
    print("\n1. WSZYSTKIE WPISY PRODUKCJA:")
    cursor.execute("""
        SELECT 
            id,
            surowiec_id,
            surowiec_nazwa,
            typ_ruchu,
            ilosc,
            ilosc_po,
            zbiornik,
            status,
            autor_login,
            autor_data,
            komentarz
        FROM magazyn_agro_ruch
        WHERE typ_ruchu = 'PRODUKCJA'
        ORDER BY autor_data DESC
        LIMIT 20
    """)
    ruchy = cursor.fetchall()
    if ruchy:
        for r in ruchy:
            print(f"  ID: {r['id']}, Zbiornik: {r['zbiornik']}, Surowiec: {r['surowiec_nazwa']}, "
                  f"Ilosc: {r['ilosc']}, Po: {r['ilosc_po']}, "
                  f"Komentarz: {r['komentarz']}, Data: {r['autor_data']}")
    else:
        print("  Brak wpisów PRODUKCJA")
    
    # Sprawdź wpisy z sesji #9
    print("\n2. WPISY Z SESJI #9:")
    cursor.execute("""
        SELECT *
        FROM magazyn_agro_ruch
        WHERE komentarz LIKE '%Sesja #9%'
        ORDER BY id DESC
    """)
    sesja9 = cursor.fetchall()
    if sesja9:
        for r in sesja9:
            print(f"  ID: {r['id']}, Zbiornik: {r['zbiornik']}, Typ: {r['typ_ruchu']}, "
                  f"Surowiec: {r['surowiec_nazwa']}, Ilosc: {r['ilosc']}, "
                  f"Komentarz: {r['komentarz']}")
    else:
        print("  Brak wpisów z sesji #9")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check_agro_ruch()
