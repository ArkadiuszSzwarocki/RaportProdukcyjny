from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT akcja, komentarz, user_login, data_ruchu FROM palety_historia WHERE data_ruchu > '2026-07-07 00:00:00' ORDER BY data_ruchu DESC LIMIT 20")
res = cur.fetchall()
for r in res:
    print(r)
