from db import get_db_connection

conn = get_db_connection(); cursor = conn.cursor()
cursor.execute("SHOW COLUMNS FROM dziennik_zmiany")
cols = cursor.fetchall()
for c in cols:
    print(c)
conn.close()
