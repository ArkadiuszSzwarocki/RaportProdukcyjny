#!/usr/bin/env python
"""Diagnose why zlecenie start failed today"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()
print(f"\n{'='*70}")
print(f"DIAGNOZA - DLACZEGO NIE MOŻNA BYŁO URUCHOMIĆ ZLECENIA NA {today}")
print(f"{'='*70}\n")

# Sprawdź plany na dzisiaj dla Workowania
cursor.execute(
    "SELECT id, produkt, status, real_start, real_stop "
    "FROM plan_produkcji "
    "WHERE sekcja='Workowanie' AND DATE(data_planu)=%s "
    "ORDER BY id DESC LIMIT 5",
    (today,)
)
pracy = cursor.fetchall()
print(f"Plany WORKOWANIE na dzisiaj ({today}):")
if pracy:
    for p in pracy:
        print(f"  ID={p['id']:5} | {p['produkt']:20} | status={p['status']:12} | start={p['real_start']} | stop={p['real_stop']}")
else:
    print("  ❌ BRAK PLANÓW NA DZISIAJ")

# Sprawdź kolejkowanie - które Zasyp się skończyły
cursor.execute(
    "SELECT id, produkt, status, real_stop "
    "FROM plan_produkcji "
    "WHERE sekcja='Zasyp' AND DATE(data_planu)=%s AND status='zakonczone' "
    "ORDER BY real_stop ASC LIMIT 5",
    (today,)
)
zasyps = cursor.fetchall()
print(f"\nProdukty ZASYP zakończone dzisiaj (kolejka do Workowania):")
if zasyps:
    for z in zasyps:
        print(f"  {z['produkt']:20} | stop={z['real_stop']}")
else:
    print("  ❌ BRAK ZAKOŃCZONYCH NA ZASYP")

# Sprawdź co jest w toku na Zasyp
cursor.execute(
    "SELECT id, produkt, status, real_start "
    "FROM plan_produkcji "
    "WHERE sekcja='Zasyp' AND DATE(data_planu)=%s AND status='w toku' "
    "LIMIT 5",
    (today,)
)
zatrudnieh = cursor.fetchall()
print(f"\nCo jest 'w toku' na ZASYP dzisiaj:")
if zatrudnieh:
    for z in zatrudnieh:
        print(f"  ID={z['id']:5} | {z['produkt']:20} | start={z['real_start']}")
else:
    print("  ✅ Nic nie jest w toku na Zasyp")

conn.close()

print(f"\n{'='*70}")
print("PRZYCZYNY:")
print("  1. Jeśli Zasyp jest 'w toku' - Workowanie czeka na zakończenie")
print("  2. Jeśli nic nie jest zakończone na Zasyp - Workowanie czeka")
print("  3. Produkt na Workowaniu != pierwszy z Zasyp - BLOKADA KOLEJKI")
print(f"{'='*70}\n")
