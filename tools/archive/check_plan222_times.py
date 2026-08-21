import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

cursor.execute("SELECT id, real_start, real_stop, status FROM plan_produkcji_agro WHERE id = 222")
print(cursor.fetchone())

cursor.close()
conn.close()
