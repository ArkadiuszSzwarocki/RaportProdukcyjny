from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM magazyn_dostawy WHERE id = 'a28ae2cb-2512-4f15'")
res = cur.fetchone()
print(res)
