#!/usr/bin/env python
"""Check exact Zasyp→Workowanie mapping - show which batch was assigned to each Workowanie"""
from app.db import get_db_connection
from datetime import date
import sys
sys.path.insert(0, '.')

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()
print(f"\n=== DOKŁADNE MAPOWANIE: Zasyp→Workowanie (data={today}) ===\n")

# 1. Pobierz wszystkie Zasypy
cursor.execute("""
    SELECT id, produkt, tonaz_rzeczywisty, status
    FROM plan_produkcji
    WHERE sekcja = 'Zasyp' AND data_planu = %s
    ORDER BY produkt, status DESC
""", (today,))

print("[DOSTĘPNE ZASYPY]:")
zasypy_by_prod = {}
for z_id, produkt, tonaz_rz, status in cursor.fetchall():
    if produkt not in zasypy_by_prod:
        zasypy_by_prod[produkt] = []
    zasypy_by_prod[produkt].append((z_id, tonaz_rz, status))
    print(f"  id={z_id} | {produkt:20} | tonaz_rz={tonaz_rz:8} | status={status}")

# 2. Dla każdego Workowania - oblicz które Zasyp powinno być wybrane (według SQL logiki)
cursor.execute("""
    SELECT id, produkt, tonaz AS plan_tonaz
    FROM plan_produkcji
    WHERE sekcja = 'Workowanie' AND data_planu = %s
    ORDER BY produkt
""", (today,))

workowania = cursor.fetchall()

print(f"\n[MAPOWANIE Workowanie←Zasyp]:")
for w_id, produkt, plan_tonaz in workowania:
    # Symuluj SQL query z refresh_bufor_queue
    matching_zasypy = zasypy_by_prod.get(produkt, [])
    if not matching_zasypy:
        selected = None
        print(f"  Workowanie id={w_id} | {produkt:20} | plan_tonaz={plan_tonaz:8} ← BRAK Zasyp")
    else:
        # Sortuj jak w SQL
        sorted_zasypy = sorted(
            matching_zasypy,
            key=lambda x: (
                0 if x[2] == 'zakonczone' else 1,  # CASE WHEN status='zakonczone'
                -x[1],  # DESC tonaz_rzeczywisty (aproksymacja real_stop)
                -x[0]   # DESC id
            )
        )
        selected = sorted_zasypy[0]  # LIMIT 1
        z_id, z_tonaz_rz, z_status = selected
        match = "✓" if z_tonaz_rz == plan_tonaz else "✗"
        print(f"  Workowanie id={w_id} | {produkt:20} | plan_tonaz={plan_tonaz:8} ← Zasyp id={z_id} (tonaz_rz={z_tonaz_rz}, status={z_status}) {match}")

cursor.close()
conn.close()
print("\n✓ = wartości się zgadzają | ✗ = mismatch\n")
