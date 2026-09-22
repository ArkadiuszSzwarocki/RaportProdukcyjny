from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

cur.execute("SHOW TABLES")
tables = [t[0] for t in cur.fetchall()]
print("Tables in database:")
for t in sorted(tables):
    print(" ", t)

conn.close()
