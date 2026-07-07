from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("UPDATE magazyn_dostawy SET status = 'OCZEKUJE' WHERE id = 'a28ae2cb-2512-4f15'")
conn.commit()
print('Updated:', cur.rowcount)
