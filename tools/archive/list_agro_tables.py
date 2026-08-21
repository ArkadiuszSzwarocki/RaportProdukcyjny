import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")
cursor.execute("SHOW TABLES")
tables = [list(r.values())[0] for r in cursor.fetchall()]
for t in sorted(tables):
    if 'agro' in t.lower() or 'zasyp' in t.lower() or 'tank' in t.lower() or 'zbior' in t.lower():
        print(t)
cursor.close()
conn.close()
