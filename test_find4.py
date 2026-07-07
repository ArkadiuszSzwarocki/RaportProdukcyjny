from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, status, lokalizacja_z, lokalizacja_do, order_ref FROM magazyn_dostawy WHERE id LIKE '%07072026091144%' OR order_ref LIKE '%07072026091144%'")
res = cur.fetchall()
print('Found:', res)
