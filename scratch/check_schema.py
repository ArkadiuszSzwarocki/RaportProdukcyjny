import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SHOW TABLES LIKE '%surowc%'")
tables = cursor.fetchall()
for t in tables:
    t_name = list(t.values())[0]
    cursor.execute(f"SHOW CREATE TABLE {t_name}")
    print(cursor.fetchone())
conn.close()
