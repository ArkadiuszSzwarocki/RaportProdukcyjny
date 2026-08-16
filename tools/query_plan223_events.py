import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection
import json

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- zasyp_etapy for plan 223 ---")
cursor.execute("SELECT * FROM zasyp_etapy WHERE plan_id = 223 ORDER BY szarza_nr, etap")
for r in cursor.fetchall():
    print(r)
    
print("--- szarze_agro for plan 223 ---")
cursor.execute("SELECT * FROM szarze_agro WHERE plan_id = 223 ORDER BY nr_szarzy")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
