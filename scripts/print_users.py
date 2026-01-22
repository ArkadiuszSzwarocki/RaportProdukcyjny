from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id, login, haslo, rola FROM uzytkownicy")
for r in cursor.fetchall():
    print(r)
conn.close()
