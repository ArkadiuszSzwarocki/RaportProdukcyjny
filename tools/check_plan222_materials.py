import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection
import json

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- magazyn_agro_ruch for plan 222 ---")
cursor.execute("SELECT * FROM magazyn_agro_ruch WHERE plan_id = 222")
for r in cursor.fetchall():
    print(r)

print("--- dosypki_agro for plan 222 ---")
cursor.execute("SELECT * FROM dosypki_agro WHERE plan_id = 222")
for r in cursor.fetchall():
    print(r)
    
cursor.close()
conn.close()
