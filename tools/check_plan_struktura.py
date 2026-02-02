from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Pokaż strukturę planu na dzisiaj
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-02'
    ORDER BY sekcja, produkt, id
""")

print("=" * 120)
print("PLAN NA 2026-02-02")
print("=" * 120)
for row in cursor.fetchall():
    print(f"ID: {row[0]:3} | Sekcja: {row[1]:12} | Produkt: {row[2]:25} | Plan: {row[3]:8} | Rzecz: {row[4]:8} | Typ: {row[5]}")

print("\n" + "=" * 120)
print("SUMY PO SEKCJACH")
print("=" * 120)

cursor.execute("""
    SELECT sekcja, SUM(tonaz) as plan, SUM(tonaz_rzeczywisty) as wykonanie
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-02'
    GROUP BY sekcja
    ORDER BY sekcja
""")

for row in cursor.fetchall():
    print(f"Sekcja: {row[0]:12} | Plan: {row[1]:10} | Wykonanie: {row[2]:10}")

conn.close()
