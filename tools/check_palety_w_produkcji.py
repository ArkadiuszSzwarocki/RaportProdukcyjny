#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza czy palety z błędnymi lokalizacjami są też przypisane do produkcji."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

# Palety z błędnymi lokalizacjami
WRONG_PALLETS = [
    (466, 'BB17', 'ACP Kwaśna'),
    (492, 'BB17', 'Bm3'),
    (511, 'BB17', 'Bm3'),
    (535, 'BB14', 'Mąka pszenna'),
    (640, 'BB01', 'WPP'),
    (641, 'BB01', 'WPP'),
]

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("\n" + "="*100)
print("SPRAWDZENIE CZY PALETY SĄ PRZYPISANE DO PRODUKCJI")
print("="*100 + "\n")

for surowiec_id, bledna_lok, nazwa in WRONG_PALLETS:
    print(f"\n{'─'*100}")
    print(f"📦 Surowiec ID={surowiec_id} | {nazwa} | Błędna lokalizacja w magazynie: {bledna_lok}")
    print(f"{'─'*100}")
    
    # Sprawdź aktualny stan w magazyn_surowce
    cursor.execute("""
        SELECT id, nazwa, stan_magazynowy, lokalizacja, nr_palety
        FROM magazyn_surowce
        WHERE id = %s
    """, (surowiec_id,))
    surowiec = cursor.fetchone()
    
    if not surowiec:
        print(f"   ❌ NIE ZNALEZIONO w magazyn_surowce!")
        continue
    
    print(f"\n   📍 Stan w magazynie:")
    print(f"      • Nazwa: {surowiec['nazwa']}")
    print(f"      • Stan magazynowy: {surowiec['stan_magazynowy']} kg")
    print(f"      • Lokalizacja: {surowiec['lokalizacja']} ← BŁĄD (to zbiornik produkcyjny!)")
    print(f"      • Nr palety: {surowiec['nr_palety']}")
    
    # Sprawdź czy jest w produkcji (magazyn_ruch)
    cursor.execute("""
        SELECT id, typ_ruchu, zbiornik, ilosc, ilosc_po, status, 
               autor_login, autor_data, komentarz
        FROM magazyn_ruch
        WHERE surowiec_id = %s
        ORDER BY autor_data DESC
        LIMIT 10
    """, (surowiec_id,))
    ruchy = cursor.fetchall()
    
    if not ruchy:
        print(f"\n   ℹ️  BRAK wpisów w magazyn_ruch (nigdy nie był w produkcji)")
    else:
        print(f"\n   📋 Historia ruchów (ostatnie {len(ruchy)} wpisów):")
        
        aktywne_w_produkcji = []
        for r in ruchy:
            status_icon = "🔵" if r['status'] == 'aktywne' else "⚪"
            zbiornik_str = r['zbiornik'] or "(brak)"
            
            if r['status'] == 'aktywne' and r['typ_ruchu'] == 'PRODUKCJA':
                aktywne_w_produkcji.append(r)
            
            print(f"      {status_icon} {r['typ_ruchu']:15} | Zbiornik: {zbiornik_str:10} | "
                  f"Ilość: {r['ilosc']:7.1f} kg → {r['ilosc_po']:7.1f} kg | "
                  f"Status: {r['status']:10} | {r['autor_data']}")
        
        if aktywne_w_produkcji:
            print(f"\n   ⚠️  AKTYWNE PRZYPISANIA DO PRODUKCJI:")
            for r in aktywne_w_produkcji:
                print(f"      🏭 Zbiornik: {r['zbiornik']} | Ilość: {r['ilosc']} kg | "
                      f"Od: {r['autor_data']} | Autor: {r['autor_login']}")
                print(f"         Komentarz: {r['komentarz'] or '(brak)'}")
        else:
            print(f"\n   ✅ NIE MA aktywnych przypisań do produkcji")

print("\n" + "="*100)
print("PODSUMOWANIE")
print("="*100)
print("""
PROBLEM:
  Te palety mają błędne lokalizacje magazynowe (BB/MZ/KO w kolumnie lokalizacja).
  To pole określa GDZIE paleta LEŻY w magazynie (regał fizyczny).
  
ROZWIĄZANIE:
  1. Jeśli paleta NIE jest w produkcji → zmień lokalizację na właściwy regał (np. R021002)
  2. Jeśli paleta JEST w produkcji → zmień lokalizację na NULL lub właściwy regał
     (zbiornik produkcyjny powinien być TYLKO w magazyn_ruch.zbiornik)
  
UŻYJ: tools/fix_bledne_lokalizacje.py
""")

conn.close()
