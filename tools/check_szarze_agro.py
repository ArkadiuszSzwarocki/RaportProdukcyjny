import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check dosypki_agro schema - it's used to track what goes into each batch
print("--- DESCRIBE dosypki_agro ---")
cursor.execute("DESCRIBE dosypki_agro")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

# Check szarze_agro (szarze = batches)
print("\n--- DESCRIBE szarze_agro ---")
cursor.execute("DESCRIBE szarze_agro")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- szarze_agro for plan_id=222 ---")
cursor.execute("SELECT * FROM szarze_agro WHERE plan_id = 222 ORDER BY id")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
