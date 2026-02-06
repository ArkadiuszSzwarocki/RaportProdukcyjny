#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź historię tworzenia Workowania[447]"""

import sys
import io
from db import get_db_connection

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*80)
print("SZUKAJ: W jakim kontekście zostało stworzone Workowanie[447]?")
print("="*80)

# Sprawd czy jest jakaś tabela z logami
cursor.execute("SHOW TABLES LIKE '%log%'")
logs_tables = cursor.fetchall()
print(f"\nTabele z logami: {[(t[0] if isinstance(t, tuple) else t) for t in logs_tables]}")

# Szukaj w szarze czy jest coś powiązanego
print("\nSzarze dla PEŁNOMLECZNY:")
cursor.execute("""
    SELECT s.id, s.plan_id, s.waga, s.data_dodania, s.status
    FROM szarze s
    JOIN plan_produkcji p ON s.plan_id = p.id
    WHERE p.produkt = 'PEŁNOMLECZNY' AND s.data_dodania >= '2026-02-06'
    ORDER BY s.id
    LIMIT 20
""")

szarze = cursor.fetchall()
for s_id, plan_id, waga, data, status in szarze:
    print(f"  Szarza[{s_id}] → Plan[{plan_id}] | {waga}kg | {data} | {status}")

# Szukaj czy Workowanie[447] ma real_start - kedy go uruchomiono?
print("\nWorkowanie[447] szczegóły:")
cursor.execute("""
    SELECT id, data_planu, produkt, tonaz, tonaz_rzeczywisty, status, real_start, real_stop
    FROM plan_produkcji
    WHERE id = 447
""")
row = cursor.fetchone()
if row:
    print(f"  ID: {row[0]}")
    print(f"  Data: {row[1]}")
    print(f"  Produkt: {row[2]}")
    print(f"  Tonaz (plan): {row[3]}")
    print(f"  Tonaz (rzeczywisty): {row[4]}")
    print(f"  Status: {row[5]}")
    print(f"  Start: {row[6]}")
    print(f"  Stop: {row[7]}")

conn.close()
