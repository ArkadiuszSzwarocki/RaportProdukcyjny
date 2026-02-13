from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = str(date.today())

# Check if Workowanie for AGRO MILK TOP exists
cursor.execute("""
    SELECT id, status, tonaz FROM plan_produkcji
    WHERE data_planu = %s AND produkt = 'AGRO MILK TOP' AND sekcja = 'Workowanie'
""", (today,))

rows = cursor.fetchall()
print(f"Workowanie entries for AGRO MILK TOP on {today}:")
if rows:
    for row in rows:
        print(f"  ID: {row[0]}, Status: {row[1]}, Tonaz: {row[2]}")
else:
    print("  BRAK - można utworzyć nowe")

# Check all Workowania for today
cursor.execute("""
    SELECT produkt, COUNT(*) as cnt FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Workowanie'
    GROUP BY produkt
""", (today,))

print(f"\nAll Workowania for {today}:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} entries")

conn.close()
