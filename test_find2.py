from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, typ, status FROM magazyn_dostawy WHERE id = '07072026091144' OR id LIKE '%07072026091144%' OR nr_wz LIKE '%07072026091144%' OR nr_zamowienia LIKE '%07072026091144%'")
res = cur.fetchall()
print('Found:', res)
