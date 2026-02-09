from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("UPDATE plan_produkcji SET uszkodzone_worki = 0 WHERE id = 451")
conn.commit()

print("✓ Przywrócono wartość do 0")

conn.close()
