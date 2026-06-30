from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT id, status FROM plan_produkcji_agro WHERE status=\'w toku\'')
print(cur.fetchall())
