from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SHOW TRIGGERS")
print(cur.fetchall())
