from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

data = date(2026, 3, 1)
pracownik_id = 16  # Andżela

print("=== OBECNOSC NA 01.03 ===")
cursor.execute("SELECT * FROM obecnosc WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, data))
rows = cursor.fetchall()
print(f"Rekordy: {len(rows)}")
for r in rows:
    print(f"  ID={r['id']}, typ={r['typ']}, ilosc={r['ilosc_godzin']}")

print()
print("=== OBSADA NA 01.03 ===")
cursor.execute("SELECT * FROM obsada_zmiany WHERE pracownik_id=%s AND data_wpisu=%s", (pracownik_id, data))
rows = cursor.fetchall()
print(f"Rekordy: {len(rows)}")
for r in rows:
    print(f"  ID={r['id']}, sekcja={r['sekcja']}")

conn.close()
