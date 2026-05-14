from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, produkt, linia, sekcja FROM plan_produkcji WHERE status='w toku' AND is_deleted=0")
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
