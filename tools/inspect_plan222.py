import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection
import json

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- Plan 222 ---")
cursor.execute("SELECT * FROM plan_produkcji_agro WHERE id = 222")
plan = cursor.fetchone()
print(json.dumps(plan, indent=2, default=str))

print("--- zasyp_etapy for plan 222 ---")
cursor.execute("SELECT * FROM zasyp_etapy WHERE plan_id = 222 ORDER BY szarza_nr, etap")
for r in cursor.fetchall():
    print(r)
    
print("--- szarze_agro for plan 222 ---")
cursor.execute("SELECT * FROM szarze_agro WHERE plan_id = 222 ORDER BY nr_szarzy")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
