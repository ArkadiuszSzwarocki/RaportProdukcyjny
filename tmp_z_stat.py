from app.db import get_db_connection
import json

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute('SELECT id, produkt, sekcja, status, tonaz_rzeczywisty FROM plan_produkcji WHERE id IN (2750, 2752, 2754)')
rows = cursor.fetchall()
for r in rows:
    print(json.dumps(r))
conn.close()
