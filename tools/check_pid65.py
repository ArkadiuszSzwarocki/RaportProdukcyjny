import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

for pid in [65]:
    print(f"--- ID {pid} ---")
    cursor.execute("SHOW TABLES")
    tables = [list(r.values())[0] if hasattr(r, 'values') else r[0] for r in cursor.fetchall()]
    for table in tables:
        try:
            cursor.execute(f"SELECT * FROM {table} WHERE id = %s", (pid,))
            res = cursor.fetchall()
            if res:
                print(f"  Found in {table}:", res)
        except:
            pass

cursor.close()
conn.close()
