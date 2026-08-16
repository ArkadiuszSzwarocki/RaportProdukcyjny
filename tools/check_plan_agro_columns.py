import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- columns of plan_produkcji_agro ---")
cursor.execute("DESCRIBE plan_produkcji_agro")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

cursor.close()
conn.close()
