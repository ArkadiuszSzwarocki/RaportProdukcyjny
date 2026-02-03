#!/usr/bin/env python3
"""
Test panelu planisty — sprawdzenie czy wykonanie (szarże) są wyświetlane
"""
import sys
sys.path.insert(0, '.')

from db import get_db_connection
from datetime import date

# Test: pobierz dane takiej jak robilibyśmy w routes_planista
conn = get_db_connection()
cursor = conn.cursor()

wybrana_data = '2026-02-03'

cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci 
    FROM plan_produkcji 
    WHERE data_planu = %s AND sekcja = 'Zasyp'
    ORDER BY kolejnosc
""", (wybrana_data,))

plany = cursor.fetchall()
plany_list = [list(p) for p in plany]

print("Testy panelu Planisty dla", wybrana_data)
print("=" * 80)

for p in plany_list:
    plan_id = p[0]
    produkt = p[2]
    tonaz_plan = p[3]
    
    # Oblicz szarże (wykonanie rzeczywiste dla Zasyp)
    cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
    szarze_result = cursor.fetchone()
    wykonanie = szarze_result[0] if szarze_result and szarze_result[0] else 0
    
    print(f"\n📋 Plan {plan_id}: {produkt}")
    print(f"   Plan (kg):        {tonaz_plan}")
    print(f"   Wykonanie (szarże): {wykonanie} kg")
    
    if wykonanie > 0:
        proc = (wykonanie / tonaz_plan * 100) if tonaz_plan > 0 else 0
        print(f"   Realizacja:       {proc:.0f}%")
    
    # Wylistuj szarże
    cursor.execute("SELECT id, waga, data_dodania FROM szarze WHERE plan_id = %s ORDER BY id", (plan_id,))
    szarze = cursor.fetchall()
    if szarze:
        print(f"   Szarże ({len(szarze)}):")
        for sz_id, waga, data in szarze:
            print(f"     - ID {sz_id}: {waga} kg ({data})")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✓ Test zakończony")
