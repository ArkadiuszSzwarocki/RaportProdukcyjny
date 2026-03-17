from app.db import get_db_connection
import json

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, DATE_FORMAT(data_planu, '%Y-%m-%d') as data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE data_planu=%s ORDER BY id", ('2026-03-18',))
rows = cur.fetchall()
print(json.dumps(rows, default=str, ensure_ascii=False, indent=2))
conn.close()
