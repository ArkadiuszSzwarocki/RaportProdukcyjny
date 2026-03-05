#!/usr/bin/env python3
"""
Test: sprawdzić jakie wartości są aktualnie zwracane z routes_planista.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Wczytaj 3 principais from Zasyp for date 2026-03-05
cursor.execute("""
    SELECT id, produkt, tonaz, tonaz_rzeczywisty, sekcja
    FROM plan_produkcji
    WHERE data_planu = '2026-03-05' AND sekcja = 'Zasyp'
    LIMIT 3
""")
plans = cursor.fetchall()

print("=== LIVE EXECUTION TEST ===\n")
for plan_id, produkt, plan_tonaz, tonaz_rzecz, sekcja in plans:
    print(f"\n📌 {produkt} (Plan ID={plan_id}, Sekcja={sekcja})")
    print(f"   Plan tonaz: {plan_tonaz} kg")
    print(f"   Tonaz rzeczywisty (DB): {tonaz_rzecz} kg")
    
    # Test: execute the EXACT SQL from routes_planista.py line 120
    sql = "SELECT COALESCE(SUM(waga), 0) + COALESCE((SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1), 0) FROM szarze WHERE plan_id = %s"
    cursor.execute(sql, (plan_id, plan_id))
    result = cursor.fetchone()
    wykonanie = result[0] if result else 0
    
    print(f"   ✅ Wykonanie (szarże + dosypki): {wykonanie} kg")
    
    # Also check OLD way (just szarže)
    cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
    old_result = cursor.fetchone()
    old_wykonanie = old_result[0] if old_result else 0
    print(f"   ❌ Wykonanie (szarże ONLY): {old_wykonanie} kg")
    
    # Check components
    cursor.execute("SELECT SUM(waga) FROM szarze WHERE plan_id = %s", (plan_id,))
    szarze = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(kg) FROM dosypki WHERE plan_id = %s AND potwierdzone = 1", (plan_id,))
    dosypki = cursor.fetchone()[0] or 0
    
    print(f"   └─ Szarże: {szarze} kg")
    print(f"   └─ Dosypki potwierdzone: {dosypki} kg")
    print(f"   └─ SUMA: {szarze + dosypki} kg")

conn.close()
