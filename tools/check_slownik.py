import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check slownik_surowcow
print("--- DESCRIBE slownik_surowcow ---")
cursor.execute("DESCRIBE slownik_surowcow")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- sample slownik_surowcow ---")
cursor.execute("SELECT * FROM slownik_surowcow LIMIT 5")
for r in cursor.fetchall():
    print(r)

# Check magazyn_agro_slownik_surowce
print("\n--- DESCRIBE magazyn_agro_slownik_surowce ---")
cursor.execute("DESCRIBE magazyn_agro_slownik_surowce")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- sample magazyn_agro_slownik_surowce ---")
cursor.execute("SELECT * FROM magazyn_agro_slownik_surowce LIMIT 5")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
