from db import get_db_connection
from datetime import date

data_dzisiaj = str(date.today())

print(f"\n{'='*70}")
print(f"ANALIZA - CO SIĘ STAŁO Z PALETĄ")
print(f"{'='*70}\n")

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdź wszystkie plany dla produktu 'test' dzisiaj w Workowanie
cursor.execute("""
    SELECT id, tonaz, status, tonaz_rzeczywisty 
    FROM plan_produkcji 
    WHERE produkt='test' AND data_planu=%s AND sekcja='Workowanie'
    ORDER BY id
""", (data_dzisiaj,))

print("WSZYSTKIE PLANY WORKOWANIE DLA PRODUKTU 'test':")
print("-" * 70)

for row in cursor.fetchall():
    plan_id, tonaz, status, tonaz_rzeczywisty = row
    print(f"ID={plan_id} | Tonaz={tonaz:6.0f} | Status={status:12s} | Realizacja={tonaz_rzeczywisty:6.0f}")

print("\n" + "="*70)
print("PROBLEM:")
print("="*70)
print("""
Mamy 2 plany Workowanie:
1. ID=367 - BUFOR (tworzony automatycznie gdy dodajemy szarżę)
2. ID=376 - PALETA (dodawana ręcznie)

Gdy dodajemy paletę, kod szuka PIERWSZEGO otwartego planu w Workowanie.
Może znaleźć Plan Palety zamiast Bufora!

ROZWIĄZANIE:
Bufor powinien być rozróżniony - np. mieć inne status lub pole.
LUB: Gdy dodajemy paletę, szukamy NAJSTARSZEGO (MIN(id)) otwartego planu.
""")

conn.close()
