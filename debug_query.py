#!/usr/bin/env python
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

current_date = date(2026, 3, 4)

# Check what query selects
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji, status
    FROM plan_produkcji
    WHERE DATE(data_planu) = %s AND status = 'zakonczone'
      AND LOWER(sekcja) = 'zasyp'
      AND (tonaz_rzeczywisty IS NULL OR tonaz_rzeczywisty < tonaz)
    ORDER BY id
""", (current_date,))

plans = cursor.fetchall()
print(f"Found {len(plans)} incomplete plans on {current_date}:")
for plan in plans:
    print(f"  id={plan['id']}, sekcja={plan['sekcja']}, produkt={plan['produkt']}, tonaz={plan['tonaz']}, tonaz_rzeczywisty={plan['tonaz_rzeczywisty']}, status={plan['status']}")

print("\nDirect check for plan 1262:")
cursor.execute("SELECT * FROM plan_produkcji WHERE id=1262")
plan_1262 = cursor.fetchone()
print(f"Plan 1262 status: {plan_1262['status']}, date: {plan_1262['data_planu']}, tonaz: {plan_1262['tonaz']}, tonaz_rzeczywisty: {plan_1262['tonaz_rzeczywisty']}")

cursor.close()
conn.close()
