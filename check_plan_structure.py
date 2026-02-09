from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdź plany dla tego samego produktu w obu sekcjach
cursor.execute("""
    SELECT id, sekcja, produkt, uszkodzone_worki, status
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND produkt = 'MILK DE LUX SPECJAL'
    ORDER BY sekcja
""", (date.today(),))

rows = cursor.fetchall()
print("=" * 70)
print("PLANY DLA PRODUKTU: MILK DE LUX SPECJAL")
print("=" * 70)

for r in rows:
    print(f"ID={r[0]:3} | sekcja={r[1]:15} | uszkodzone_worki={r[3]}")

print("\n" + "=" * 70)
print("RÓŻNE PLANY = RÓŻNE SEKCJE")
print("=" * 70)

# Pobierz all produkty dzisiaj w Zasyp
cursor.execute("""
    SELECT DISTINCT produkt FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp'
""", (date.today(),))

products = [r[0] for r in cursor.fetchall()]
print(f"Produkty w Zasyp: {products}")

# Dla każdego produktu sprawdź czy ma plan w Workowaniu
for prod in products[:3]:
    cursor.execute("""
        SELECT COUNT(*) FROM plan_produkcji 
        WHERE DATE(data_planu) = %s AND produkt = %s AND sekcja = 'Workowanie'
    """, (date.today(), prod))
    count = cursor.fetchone()[0]
    print(f"  {prod:25} - Workowanie: {'✓ ma' if count > 0 else '✗ brak'}")

conn.close()
