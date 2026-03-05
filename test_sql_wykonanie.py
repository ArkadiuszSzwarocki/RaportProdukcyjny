#!/usr/bin/env python3
"""Direct SQL test - check what values should be displayed for Wykonanie"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Get the 3 main plans for Zasyp on 2026-03-05
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty
    FROM plan_produkcji
    WHERE data_planu = '2026-03-05' AND sekcja = 'Zasyp'
    ORDER BY kolejnosc
    LIMIT 5
""")

plans = cursor.fetchall()

print("\n" + "="*80)
print("🔍 TEST: SQL from routes_planista.py line 120")
print("="*80 + "\n")

for plan_id, produkt, plan_tonaz, tonaz_rzecz in plans:
    print(f"📌 {produkt.ljust(20)} (ID={plan_id})")
    print(f"   Plan tonaz: {plan_tonaz} kg")
    print(f"   Tonaz rzeczywisty: {tonaz_rzecz} kg")
    
    # Test the CURRENT SQL from routes_planista.py line 120
    sql_new = """SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1), 0) FROM szarze WHERE plan_id = %s"""
    cursor.execute(sql_new, (plan_id, plan_id))
    new_result = cursor.fetchone()[0]
    
    # Also test old way (just szarze)
    cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
    old_result = cursor.fetchone()[0] or 0
    
    # Get components
    cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
    szarze_kg = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1", (plan_id,))
    dosypki_kg = cursor.fetchone()[0] or 0
    
    print(f"   ├─ Szarże:          {szarze_kg:>6} kg")
    print(f"   ├─ Dosypki potwierdz:{dosypki_kg:>6} kg")
    print(f"   ├─ SUMA:             {szarze_kg + dosypki_kg:>6} kg")
    print(f"   ├─ ❌ Stary SQL:      {old_result:>6} kg (ONLY szarze, WRONG)")
    print(f"   └─ ✅ Nowy SQL:      {new_result:>6} kg (szarze + dosypki, CORRECT)")
    
    if new_result != old_result:
        print(f"   ⚠️  DIFFERENCE: {new_result - old_result} kg \n")
    else:
        print(f"   ℹ️  Same result (no dosypki) \n")

conn.close()

print("="*80)
print("✅ Test complete - values above should match UI after server restart")
print("="*80 + "\n")
