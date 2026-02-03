#!/usr/bin/env python3
"""
Test widoku magazynu — sprawdzenie czy zatwierdzone palety są wyświetlane
"""
import sys
sys.path.insert(0, '.')

from db import get_db_connection
from utils.queries import QueryHelper
from datetime import date

dzisiaj = str(date.today())

# Test: pobierz zatwierdzone palety jak robilibyśmy w app.py
print(f"Test magazynu dla dnia {dzisiaj}")
print("=" * 80)

# Pobierz zatwierdzone palety
confirmed = QueryHelper.get_paletki_magazyn(dzisiaj)
print(f"\n✓ Zatwierdzone palety (status='przyjeta'): {len(confirmed)} szt.")

if confirmed:
    total_waga = 0
    for i, row in enumerate(confirmed, 1):
        # row: (id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji, status, czas_potwierdzenia_s)
        palete_id = row[0]
        waga = row[2]
        produkt = row[6]
        status = row[8]
        print(f"\n  {i}. Paleta ID {palete_id}")
        print(f"     Produkt: {produkt}")
        print(f"     Waga: {waga} kg")
        print(f"     Status: {status}")
        total_waga += waga if waga else 0
    
    print(f"\n  RAZEM: {total_waga} kg")
else:
    print("  (brak zatwierdz palet)")

# Pokaż również ile jest palet oczekujących
print(f"\n" + "-" * 80)
print("Porównanie: palety oczekujące vs zatwierdzone\n")

conn = get_db_connection()
cursor = conn.cursor()

# Wszystkie palety dla dzisiaj
cursor.execute("""
    SELECT COUNT(*), COALESCE(SUM(waga),0), COALESCE(SUM(CASE WHEN status='do_przyjecia' THEN waga ELSE 0 END),0), 
           COALESCE(SUM(CASE WHEN status='przyjeta' THEN waga ELSE 0 END),0)
    FROM palety_workowanie 
    WHERE DATE(data_dodania) = %s AND waga > 0
""", (dzisiaj,))
row = cursor.fetchone()

if row:
    all_count, all_waga, pending_waga, confirmed_waga = row
    print(f"  Wszystkie palety: {all_count} szt, {all_waga} kg")
    print(f"  - Oczekujące: {pending_waga} kg")
    print(f"  - Zatwierdzone: {confirmed_waga} kg")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✓ Test zakończony")
