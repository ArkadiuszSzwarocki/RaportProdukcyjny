from app.db import get_db_connection
import json

conn = get_db_connection()
cur = conn.cursor()
cur.execute('SHOW INDEX FROM plan_produkcji')
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
result = [dict(zip(cols, r)) for r in rows]
print(json.dumps(result, default=str, indent=2))
cur.close()
conn.close()
