#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza palety z błędnymi lokalizacjami (BB/MZ/KO w magazynie)."""
import sys
import os
import re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection, get_table_name

# Wzorce lokalizacji produkcyjnych (NIE mogą być w magazynie!)
PRODUCTION_PATTERNS = [
    r'^BB\d{1,2}$',  # BB01, BB02, ..., BB24
    r'^MZ\d{1,2}$',  # MZ01, MZ02, ..., MZ24
    r'^MZ\d{2}-\d{2}$',  # MZ05-01, MZ06-01
    r'^KO\d{1,2}$',  # KO01, KO02, ..., KO24
]

def is_production_location(lokalizacja):
    """Sprawdza czy lokalizacja to kod produkcyjny (zbiornik)."""
    if not lokalizacja:
        return False
    for pattern in PRODUCTION_PATTERNS:
        if re.match(pattern, str(lokalizacja).upper().strip()):
            return True
    return False

conn = get_db_connection()
try:
    cursor = conn.cursor(dictionary=True)
    
    print("\n" + "="*100)
    print("PALETY Z BŁĘDNYMI LOKALIZACJAMI (kody zbiorników produkcyjnych w magazynie)")
    print("="*100 + "\n")
    
    tables = [
        ('magazyn_surowce', 'Agro', 'surowce'),
        ('magazyn_palety', 'Agro', 'wyroby gotowe'),
        ('magazyn_opakowania', 'Agro', 'opakowania'),
        ('magazyn_surowce', 'PSD', 'surowce'),
        ('magazyn_palety', 'PSD', 'wyroby gotowe'),
        ('magazyn_opakowania', 'PSD', 'opakowania'),
    ]
    
    total_bledne = 0
    wszystkie_bledne = []
    
    for table_base, linia, typ in tables:
        table = get_table_name(table_base, linia)
        
        # Pobierz wszystkie palety z lokalizacją (uproszczone zapytanie)
        if table_base == 'magazyn_palety':
            cursor.execute(
                f"SELECT id, nr_palety, produkt as nazwa, lokalizacja "
                f"FROM {table} "
                f"WHERE lokalizacja IS NOT NULL AND lokalizacja != '' "
                f"ORDER BY id DESC"
            )
        else:
            cursor.execute(
                f"SELECT id, nr_palety, nazwa, lokalizacja "
                f"FROM {table} "
                f"WHERE lokalizacja IS NOT NULL AND lokalizacja != '' "
                f"ORDER BY id DESC"
            )
        palety = cursor.fetchall()
        
        bledne = [p for p in palety if is_production_location(p['lokalizacja'])]
        
        if bledne:
            total_bledne += len(bledne)
            print(f"🚨 {linia} - {typ.upper()}: {len(bledne)}/{len(palety)} palet z błędną lokalizacją")
            print(f"{'─'*100}")
            
            for p in bledne[:5]:  # Pokaż pierwsze 5
                wszystkie_bledne.append((linia, typ, p))
                print(f"   ID: {p['id']:>5} | {p['nr_palety']:<25} | "
                      f"❌ Lokalizacja: {p['lokalizacja']:<10} | "
                      f"{(p.get('nazwa') or ''):<40}")
            
            if len(bledne) > 5:
                print(f"   ... i {len(bledne) - 5} więcej")
            print()
    
    print("="*100)
    print(f"PODSUMOWANIE: {total_bledne} palet z błędnymi lokalizacjami (kody zbiorników zamiast regałów)")
    print("="*100)
    
    if total_bledne > 0:
        print("\n❗ PROBLEM:")
        print("   Kody BB*, MZ*, KO* to zbiorniki produkcyjne - NIE mogą być używane jako lokalizacje magazynowe!")
        print("   Prawidłowe lokalizacje magazynowe to np: R021002, R030601, itd.")
        print("\n💡 ROZWIĄZANIA:")
        print("   1. Poprawić ręcznie lokalizacje w systemie na prawidłowe (regały R*)")
        print("   2. Dodać walidację w kodzie aby zapobiec wprowadzaniu błędnych lokalizacji")
        print("   3. Uruchomić skrypt migracyjny aby automatycznie poprawić błędne wartości")
    
    # Statystyki po typach lokalizacji
    print("\n" + "="*100)
    print("STATYSTYKA BŁĘDNYCH LOKALIZACJI:")
    print("="*100)
    
    lokalizacje_count = {}
    for linia, typ, p in wszystkie_bledne:
        lok = p['lokalizacja'].upper()
        if lok not in lokalizacje_count:
            lokalizacje_count[lok] = 0
        lokalizacje_count[lok] += 1
    
    for lok in sorted(lokalizacje_count.keys()):
        print(f"   {lok}: {lokalizacje_count[lok]} palet")
    
finally:
    conn.close()
