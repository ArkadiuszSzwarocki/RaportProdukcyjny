from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT akcja, komentarz, created_at, user_login FROM palety_historia WHERE komentarz LIKE '%07072026091144%' ORDER BY created_at")
res = cur.fetchall()
for r in res:
    print(r)
