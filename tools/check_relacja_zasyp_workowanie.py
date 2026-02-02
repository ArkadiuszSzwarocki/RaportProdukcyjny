from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 150)
print("ZASYP - SZARŻA (plan_id) vs WORKOWANIE")
print("=" * 150)

# Pokaż Zasyp szarże
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, typ_produkcji
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-02' AND sekcja = 'Zasyp'
    ORDER BY produkt
""")

print("\nZASYP SZARŻE:")
for row in cursor.fetchall():
    plan_id = row[0]
    produkt = row[2]
    tonaz = row[3]
    typ = row[4]
    print(f"  plan_id={plan_id} | produkt={produkt:20} | tonaz={tonaz} | typ={typ}")

# Pokaż Workowanie
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz_rzeczywisty, typ_produkcji
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-02' AND sekcja = 'Workowanie'
    ORDER BY produkt
""")

print("\nWORKOWANIE:")
for row in cursor.fetchall():
    plan_id = row[0]
    produkt = row[2]
    rzeczywisty = row[3]
    typ = row[4]
    print(f"  plan_id={plan_id} | produkt={produkt:20} | rzeczywisty={rzeczywisty} | typ={typ}")

# Pokaż paletki w Workowaniu
print("\nPALETKI W WORKOWANIU:")
cursor.execute("""
    SELECT plan_id, COUNT(*), SUM(waga)
    FROM palety_workowanie
    WHERE plan_id IN (SELECT id FROM plan_produkcji WHERE data_planu='2026-02-02' AND sekcja='Workowanie')
    GROUP BY plan_id
""")
for row in cursor.fetchall():
    print(f"  plan_id={row[0]} | count={row[1]} | suma_wagi={row[2]}")

conn.close()
