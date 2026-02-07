from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()

# Check all plans for Zasyp
cursor.execute(
    "SELECT id, produkt, status, sekcja FROM plan_produkcji "
    "WHERE DATE(data_planu)=%s AND sekcja IN ('Zasyp', 'Workowanie') "
    "ORDER BY sekcja, id",
    (today,)
)
plans = cursor.fetchall()

print(f"All plans for {today}:\n")
for plan_id, produkt, status, sekcja in plans:
    print(f"{sekcja:12} ID {plan_id:3d}: {produkt:15s} - {status}")

conn.close()
