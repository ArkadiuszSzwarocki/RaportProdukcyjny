from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT * FROM magazyn_dostawy WHERE id = '07072026091144'")
res = cur.fetchall()
print(res)
