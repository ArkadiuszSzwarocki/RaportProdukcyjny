from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

print("=== SPRAWDZENIE TABELI nadgodziny ===")
cursor.execute("SELECT * FROM nadgodziny")
rows = cursor.fetchall()
print(f"Wszystkie rekordy w tabeli nadgodziny: {len(rows)}")
for r in rows:
    print(f"  ID={r['id']}, pracownik={r['pracownik_id']}, data={r['data']}, ilosc={r['ilosc_nadgodzin']}, status={r['status']}")

print()
print("=== SPRAWDZENIE DLA pracownik_id=16 ===")
cursor.execute("SELECT * FROM nadgodziny WHERE pracownik_id=16")
rows16 = cursor.fetchall()
print(f"Rekordy dla pracownika 16: {len(rows16)}")
for r in rows16:
    print(f"  ID={r['id']}, data={r['data']}, ilosc={r['ilosc_nadgodzin']}, status={r['status']}")

conn.close()
