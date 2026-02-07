#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź strukturę palety_workowanie i powiązania"""

import sys
import io
from datetime import date
from db import get_db_connection

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor()

dzisiaj = str(date.today())

print("\nKOLUMNY W palety_workowanie:")
cursor.execute("DESCRIBE palety_workowanie")
cols_palety = [c[0] for c in cursor.fetchall()]
for col in cols_palety:
    print(f"  - {col}")

print(f"\n\nPowiązania Zasyp <-> Workowanie poprzez palety_workowanie (dzisiaj: {dzisiaj}):")
print("-" * 80)

# Pobierz wszystkie Zasypy i sprawdź które mają powiązane pajęty
cursor.execute("""
    SELECT id, produkt, tonaz_rzeczywisty
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Zasyp'
    ORDER BY id
""", (dzisiaj,))

zasypy = cursor.fetchall()
for zasyp_id, prod, tonaz_zasyp in zasypy:
    cursor.execute("""
        SELECT waga, plan_id FROM palety_workowanie
        WHERE plan_id = %s
        LIMIT 1
    """, (zasyp_id,))
    
    palets = cursor.fetchall()
    if palets:
        total_waga = sum(p[0] for p in palets)
        plan_ids = set(p[1] for p in palets)
        print(f"  ✓ Zasyp[{zasyp_id:3d}] {prod:20s} → {len(palets)} palet ({total_waga}kg) → plan_id: {plan_ids}")
    else:
        print(f"  ❌ Zasyp[{zasyp_id:3d}] {prod:20s} → BRAK PALET!")

print(f"\n\nWszystkie Workowania dzisiaj (powinno być powiązania):")
print("-" * 80)
cursor.execute("""
    SELECT id, produkt, tonaz_rzeczywisty, status
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Workowanie'
    ORDER BY id
""", (dzisiaj,))

workowania = cursor.fetchall()
for wo_id, prod, tonaz, status in workowania:
    print(f"  Workowanie[{wo_id:3d}] {prod:20s} | {tonaz}kg | {status}")

conn.close()
