import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- DESCRIBE zasyp_etapy_parametry ---")
cursor.execute("DESCRIBE zasyp_etapy_parametry")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])
    
print("--- Recent rows in zasyp_etapy_parametry ---")
cursor.execute("SELECT * FROM zasyp_etapy_parametry ORDER BY id DESC LIMIT 10")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
