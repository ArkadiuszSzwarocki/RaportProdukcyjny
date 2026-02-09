from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Query z routes_planista.py
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, kolejnosc, real_start, real_stop, 
           tonaz_rzeczywisty, typ_produkcji, wyjasnienie_rozbieznosci, COALESCE(uszkodzone_worki, 0)
    FROM plan_produkcji 
    WHERE data_planu = %s AND LOWER(sekcja) IN ('zasyp','czyszczenie')
    ORDER BY kolejnosc
""", (date.today(),))

rows = cursor.fetchall()
print("=" * 70)
print(f"Query z routes_planista.py - kolumn: {len(rows[0]) if rows else 0}")
print("=" * 70)

for i, row in enumerate(rows[:5]):
    print(f"\nRzad {i+1} (ID={row[0]}):")
    print(f"  p[0] (id)                = {row[0]}")
    print(f"  p[1] (sekcja)            = {row[1]}")
    print(f"  p[2] (produkt)           = {row[2]}")
    print(f"  p[3] (tonaz)             = {row[3]}")
    print(f"  p[11] (uszkodzone_worki) = {row[11]}")

conn.close()
