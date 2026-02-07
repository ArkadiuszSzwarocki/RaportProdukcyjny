from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Check if there are any Zasyp plans for same products/date
cursor.execute("""
    SELECT id, produkt, tonaz, status, sekcja, DATE(data_planu)
    FROM plan_produkcji
    WHERE DATE(data_planu) = CURDATE()
    AND produkt IN ('retrt', 'sf')
    ORDER BY sekcja, id
""")

plans = cursor.fetchall()
print(f"=== PLANS FOR retrt/sf TODAY ===")
if plans:
    for p in plans:
        print(f"  ID {p[0]}: {p[1]} | sekcja={p[4]} | status={p[3]}")
else:
    print("  Brak planów!")

# Check if maybe these Workowanie plans were auto-created?
print()
print("Plan 513/515 are Workowanie - probably auto-created without Zasyp source")
print("Correct workflow:")
print("  1. Add plan in Planowanie → goes to Zasyp")  
print("  2. Click START in Zasyp → creates szarża + auto-creates Workowanie")
print("  3. Workowanie only appears when szarża exists")

cursor.close()
conn.close()
