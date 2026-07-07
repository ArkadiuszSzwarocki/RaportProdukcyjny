from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("DESCRIBE magazyn_dostawy")
print(cur.fetchall())
