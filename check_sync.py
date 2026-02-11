#!/usr/bin/env python
"""Check if Zasyp.tonaz_rzeczywisty → bufor.tonaz_rzeczywisty → Workowanie.plan are synchronized"""
from app.db import get_db_connection
from datetime import date
import sys
sys.path.insert(0, '.')

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()
print(f"\n=== SYNCHRONIZACJA: Zasyp → Bufor → Workowanie (data={today}) ===\n")

# 1. Pobierz Zasypy dzisiaj
cursor.execute("""
    SELECT 
        id, produkt, tonaz, tonaz_rzeczywisty, status
    FROM plan_produkcji
    WHERE sekcja = 'Zasyp' AND data_planu = %s
    ORDER BY produkt
""", (today,))

zasypy = cursor.fetchall()
print(f"[ZASYP] ({len(zasypy)} wpisów):")
zasyp_map = {}
for z_id, produkt, tonaz, tonaz_rzeczywisty, status in zasypy:
    print(f"  id={z_id} | {produkt:20} | tonaz={tonaz} | tonaz_rz={tonaz_rzeczywisty} | status={status}")
    zasyp_map[produkt] = tonaz_rzeczywisty

# 2. Pobierz Bufor dzisiaj
cursor.execute("""
    SELECT 
        id, produkt, tonaz_rzeczywisty, spakowano
    FROM bufor
    WHERE data_planu = %s AND status = 'aktywny'
    ORDER BY produkt
""", (today,))

bufor_entries = cursor.fetchall()
print(f"\n[BUFOR] ({len(bufor_entries)} wpisów aktywnych):")
for b_id, produkt, tonaz_rz, spakowano in bufor_entries:
    expected_from_zasyp = zasyp_map.get(produkt, 'N/A')
    match = "✓" if tonaz_rz == expected_from_zasyp else "✗"
    print(f"  id={b_id} | {produkt:20} | tonaz_rz={tonaz_rz} (oczekiwano z Zasyp: {expected_from_zasyp}) {match} | spakowano={spakowano}")

# 3. Pobierz Workowanie dzisiaj
cursor.execute("""
    SELECT 
        id, produkt, tonaz AS plan_tonaz, tonaz_rzeczywisty, status
    FROM plan_produkcji
    WHERE sekcja = 'Workowanie' AND data_planu = %s
    ORDER BY produkt
""", (today,))

workowanie = cursor.fetchall()
print(f"\n[WORKOWANIE] ({len(workowanie)} wpisów):")
for w_id, produkt, plan_tonaz, tonaz_rz, status in workowanie:
    expected_from_bufor = zasyp_map.get(produkt, 'N/A')
    match = "✓" if plan_tonaz == expected_from_bufor else "✗"
    print(f"  id={w_id} | {produkt:20} | plan/tonaz={plan_tonaz} (oczekiwano z bufor/Zasyp: {expected_from_bufor}) {match} | tonaz_rz={tonaz_rz} | status={status}")

cursor.close()
conn.close()
print("\n✓ = wartości się zgadzają | ✗ = mismatch\n")
