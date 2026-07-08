from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("SHOW TABLES LIKE '%przesunieci%'")
print('Tables with przesunieci:', cur.fetchall())

cur.execute("SHOW TABLES LIKE '%dostawy%'")
print('Tables with dostawy:', cur.fetchall())
