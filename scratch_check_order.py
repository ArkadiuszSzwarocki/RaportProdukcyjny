import json
from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

pallet_no = 'SUR000001789020821513'

print("=== ZLECENIE f6ab854c-06d0-4647-9150-ebb15a2d7717 ===")
cur.execute("SELECT * FROM magazyn_dostawy WHERE id = 'f6ab854c-06d0-4647-9150-ebb15a2d7717'")
row = cur.fetchone()
print(row)

print("\n=== KTO STWORZYŁ ZLECENIE f6ab854c... (sprawdzenie logów / aktywności o 10:05) ===")
cur.execute("""
    SELECT * FROM aktywne_sesje WHERE last_seen >= '2026-09-17 10:00:00' AND last_seen <= '2026-09-17 10:15:00'
""")
for s in cur.fetchall():
    print("Aktywna sesja ~10:05:", s)

conn.close()
