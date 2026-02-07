import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, kolejnosc FROM plan_produkcji WHERE data_planu = %s ORDER BY id", ('2026-01-23',))
rows = cur.fetchall()
print('Total rows:', len(rows))
for r in rows:
    print(r)
conn.close()
