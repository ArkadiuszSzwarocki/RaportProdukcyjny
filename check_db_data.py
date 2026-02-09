from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdź rzeczywiste dane w DB
cursor.execute("""
    SELECT id, produkt, tonaz, COALESCE(uszkodzone_worki, 0) as uszk
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s 
    ORDER BY id DESC
    LIMIT 10
""", (date.today(),))

rows = cursor.fetchall()
print("=" * 60)
print("DANE W BAZIE DANYCH")
print("=" * 60)
print(f"{'ID':5} {'Produkt':15} {'Tonaz':10} {'Uszkodzone':10}")
print("-" * 50)
for r in rows:
    print(f"{r[0]:<5} {r[1]:15} {r[2]:>10.0f} {r[3]:>10}")

conn.close()
