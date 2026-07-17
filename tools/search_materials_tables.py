import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("USE biblioteka")
cursor.execute("SHOW TABLES")
tables = [list(r.values())[0] if hasattr(r, 'values') else r[0] for r in cursor.fetchall()]
for t in sorted(tables):
    t_lower = t.lower()
    if 'pozycj' in t_lower or 'recept' in t_lower or 'sklad' in t_lower or 'mater' in t_lower or 'surow' in t_lower:
        print(t)
cursor.close()
conn.close()
