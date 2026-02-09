#!/usr/bin/env python3
"""Recreate Testowy2 and Testowy4 for testing"""
from app.db import get_db_connection
from datetime import date, datetime, timedelta

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()
data_planu = today

print(f"\n🔄 Odtwarzanie Testowy2 i Testowy4 na dzień {data_planu}...\n")

# Create Zasyp plans for Testowy2 and Testowy4
testowy_plans = [
    {
        'produkt': 'Testowy2',
        'tonaz_rzeczywisty': 3000,
        'real_start': datetime.combine(today, datetime.min.time()).replace(hour=0, minute=51, second=9),
        'real_stop': None
    },
    {
        'produkt': 'Testowy4', 
        'tonaz_rzeczywisty': 40000,
        'real_start': datetime.combine(today, datetime.min.time()).replace(hour=0, minute=54, second=9),
        'real_stop': None
    }
]

zasyp_ids = []
for plan in testowy_plans:
    cursor.execute("""
        INSERT INTO plan_produkcji 
        (sekcja, data_planu, produkt, tonaz_rzeczywisty, status, real_start, real_stop)
        VALUES ('Zasyp', %s, %s, %s, 'zakonczone', %s, %s)
    """, (data_planu, plan['produkt'], plan['tonaz_rzeczywisty'], plan['real_start'], plan['real_stop']))
    
    zasyp_id = cursor.lastrowid
    zasyp_ids.append(zasyp_id)
    print(f"  ✓ Zasyp {plan['produkt']}: ID={zasyp_id}")

# Create Workowanie plans for each
for i, plan in enumerate(testowy_plans):
    cursor.execute("""
        INSERT INTO plan_produkcji 
        (sekcja, data_planu, produkt, tonaz, tonaz_rzeczywisty, status)
        VALUES ('Workowanie', %s, %s, %s, %s, 'zaplanowane')
    """, (data_planu, plan['produkt'], plan['tonaz_rzeczywisty'], 0))
    
    workowanie_id = cursor.lastrowid
    print(f"  ✓ Workowanie {plan['produkt']}: ID={workowanie_id}")

conn.commit()

print(f"\n✅ Testowy2 i Testowy4 odtworzone!")
print(f"   Będą dostępne po refresh bufor\n")

cursor.close()
conn.close()
