from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = str(date.today())

# Check Zasyp status for AGRO MILK TOP
cursor.execute("""
    SELECT id, produkt, status, tonaz_rzeczywisty 
    FROM plan_produkcji
    WHERE data_planu = %s AND produkt = 'AGRO MILK TOP' AND sekcja = 'Zasyp'
""", (today,))

row = cursor.fetchone()
if row:
    print(f"Zasyp AGRO MILK TOP:")
    print(f"  ID: {row[0]}")
    print(f"  Status: '{row[2]}'")
    print(f"  Tonaz: {row[3]}")
else:
    print("Nie znaleziono Zasypu AGRO MILK TOP dla dzisiaj")

# Check all Zasyp for today
cursor.execute("""
    SELECT produkt, status FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Zasyp'
    ORDER BY id DESC
    LIMIT 5
""", (today,))

print(f"\nWszystkie Zasypy dla {today}:")
for row in cursor.fetchall():
    print(f"  - {row[0]:20} | Status: '{row[1]}'")

conn.close()
