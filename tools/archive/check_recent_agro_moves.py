import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- Recent magazyn_agro_ruch ---")
cursor.execute("SELECT * FROM magazyn_agro_ruch ORDER BY id DESC LIMIT 20")
for r in cursor.fetchall():
    print(r['id'], r['surowiec_id'], r['surowiec_nazwa'], r['typ_ruchu'], r['ilosc'], r['plan_id'], r['zbiornik'], r['autor_data'])

cursor.close()
conn.close()
