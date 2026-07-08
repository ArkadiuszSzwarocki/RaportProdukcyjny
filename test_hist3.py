from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT akcja, komentarz, data_ruchu, user_login FROM palety_historia WHERE komentarz LIKE '%07072026091144%' ORDER BY data_ruchu")
res = cur.fetchall()
for r in res:
    print(r)
