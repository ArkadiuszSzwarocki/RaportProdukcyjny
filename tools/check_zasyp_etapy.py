import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check zasyp_etapy for plan 222 - these contain recipe/stage info
print("--- DESCRIBE zasyp_etapy ---")
cursor.execute("DESCRIBE zasyp_etapy")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- zasyp_etapy for plan_id=222 LIMIT 10 ---")
cursor.execute("SELECT * FROM zasyp_etapy WHERE plan_id = 222 ORDER BY id LIMIT 10")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
