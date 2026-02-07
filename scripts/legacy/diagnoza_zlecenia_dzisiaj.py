#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnoza: sprawdź zlecenia dzisiaj w buforze i workowaniu"""

import sys
import io
from datetime import date
from db import get_db_connection

# UTF-8 dla Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

dzisiaj = str(date.today())

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*80)
print(f"DIAGNOZA ZLECEŃ NA DZISIAJ: {dzisiaj}")
print("="*80)

# 1. Zlecenia ZASYP
print("\n[1] ZLECENIA ZASYP:")
print("-" * 80)
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty, status, real_start
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Zasyp'
    ORDER BY id
""", (dzisiaj,))

zasypy = cursor.fetchall()
if not zasypy:
    print("  ❌ BEZ ZLECEŃ ZASYP!")
else:
    for i, (id, prod, tonaz, tonaz_rz, status, real_start) in enumerate(zasypy, 1):
        print(f"  {i}. ID={id:3d} | Produkt: {prod:20s} | Plan: {tonaz}kg | Real: {tonaz_rz} | Status: {status:12s}")

# 2. Zlecenia WORKOWANIE
print("\n[2] ZLECENIA WORKOWANIE:")
print("-" * 80)
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty, status, plan_id
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Workowanie'
    ORDER BY id
""", (dzisiaj,))

workowania = cursor.fetchall()
if not workowania:
    print("  ❌ BEZ ZLECEŃ WORKOWANIE!")
else:
    for i, (id, prod, tonaz, tonaz_rz, status, plan_id) in enumerate(workowania, 1):
        print(f"  {i}. ID={id:3d} | Produkt: {prod:20s} | Plan: {tonaz}kg | Real: {tonaz_rz} | Status: {status:12s} | Plan_ID: {plan_id}")

# 3. Powiązania: Które ZASYP mają odpowiadające WORKOWANIE?
print("\n[3] POWIĄZANIA ZASYP <-> WORKOWANIE:")
print("-" * 80)
if zasypy:
    for zasyp_id, prod, tonaz, tonaz_rz, status, _ in zasypy:
        # Szukaj odpowiadającego workowania
        cursor.execute("""
            SELECT id, tonaz_rzeczywisty, status
            FROM plan_produkcji
            WHERE data_planu = %s AND sekcja = 'Workowanie' AND plan_id = %s
        """, (dzisiaj, zasyp_id))
        result = cursor.fetchone()
        if result:
            wo_id, wo_tonaz_rz, wo_status = result
            print(f"  ✓ Zasyp[{zasyp_id}] → Workowanie[{wo_id}] | {prod} | Zasyp_Real: {tonaz_rz} | Work_Real: {wo_tonaz_rz}")
        else:
            print(f"  ❌ Zasyp[{zasyp_id}] → BRAK Workowania! | {prod}")

# 4. Powiązania: Które WORKOWANIE nie mają odpowiadającego ZASYP?
print("\n[4] OSIEROCONE WORKOWANIA (bez Zasypu):")
print("-" * 80)
cursor.execute("""
    SELECT w.id, w.produkt, w.tonaz_rzeczywisty, w.plan_id
    FROM plan_produkcji w
    LEFT JOIN plan_produkcji z ON z.id = w.plan_id AND z.sekcja = 'Zasyp'
    WHERE w.data_planu = %s AND w.sekcja = 'Workowanie' AND z.id IS NULL
""", (dzisiaj,))

osierocone = cursor.fetchall()
if osierocone:
    for wo_id, prod, tonaz_rz, plan_id in osierocone:
        print(f"  ⚠️  Workowanie[{wo_id}] → plan_id:{plan_id} (NIE ISTNIEJE) | {prod}")
else:
    print("  ✓ Wszystkie Workowania mają odpowiadające Zasypy")

# 5. Sumy w BUFORZE
print("\n[5] WAGI W PALET_WORKOWANIE:")
print("-" * 80)
cursor.execute("""
    SELECT plan_id, SUM(waga) as waga_total
    FROM palety_workowanie
    WHERE plan_id IN (
        SELECT id FROM plan_produkcji
        WHERE data_planu = %s AND sekcja = 'Workowanie'
    )
    GROUP BY plan_id
""", (dzisiaj,))

palety_sum = cursor.fetchall()
if palety_sum:
    for plan_id, waga in palety_sum:
        print(f"  - Workowanie[plan_id={plan_id}] | Palet: {waga}kg")
else:
    print("  ❌ BRAK PALET W BUFORZE!")

conn.close()
print("\n" + "="*80)
