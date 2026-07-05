
from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute('SELECT id, status, potwierdzone_at FROM magazyn_dostawy ORDER BY potwierdzone_at DESC LIMIT 5;')
for row in cur.fetchall():
    print(row['id'], row['status'], row['potwierdzone_at'])

