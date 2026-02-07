#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź pałęty które trafiły do pierwszego Workowania"""

import sys
import io
from db import get_db_connection

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor()

print("\nPAŁĘTY W WORKOWANIU[447]:")
print("-" * 80)

cursor.execute("""
    SELECT id, plan_id, waga, status
    FROM palety_workowanie
    WHERE plan_id = 447
""")

palety = cursor.fetchall()
print(f"Znaleziono: {len(palety)} palet\n")

total = 0
for id, plan_id, waga, status in palety:
    print(f"  Pałęta[{id:4d}] dla Workowania[{plan_id}] | {waga}kg | {status}")
    total += waga

print(f"\nRAZEM: {total}kg")

# Sprawdź czy to jest wciąż niedokończone czy co
print("\n\nKTO MA PLAN_ID 447 W TABELI plan_produkcji?")
cursor.execute("SELECT sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE id = 447")
row = cursor.fetchone()
if row:
    sekcja, produkt, tonaz, tonaz_rzecz, status = row
    print(f"  ID=447: {sekcja:12s} | {produkt:20s} | Plan: {tonaz}kg | Real: {tonaz_rzecz}kg | Status: {status}")

# Ale czekaj - skąd się wzięło Workowanie[447]? Z którego Zasypu?
print("\n\nSZUKAJ POWIĄZANIA - które Zasyp → Workowanie[447]?")
cursor.execute("""
    SELECT z.id, z.produkt, z.tonaz_rzeczywisty
    FROM plan_produkcji z
    WHERE z.data_planu = '2026-02-06' AND z.sekcja = 'Zasyp' AND z.produkt = 'PEŁNOMLECZNY'
""")

zasyp = cursor.fetchone()
if zasyp:
    z_id, prod, tonaz = zasyp
    print(f"  Zasyp[{z_id}] PEŁNOMLECZNY | {tonaz}kg")
    print(f"  → Workowanie[447] został utworzony dla tego Zasypu!")

conn.close()
