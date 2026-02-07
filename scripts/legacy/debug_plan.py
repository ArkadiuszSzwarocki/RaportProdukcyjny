import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()
wybrana = date.today()
for sekcja in ['Zasyp', 'Magazyn', 'Workowanie']:
    q = ("SELECT id, produkt, tonaz, status, TIME_FORMAT(real_start, '%H:%i'), TIME_FORMAT(real_stop, '%H:%i'), TIMESTAMPDIFF(MINUTE, real_start, real_stop) "
         "FROM plan_produkcji WHERE data_planu = %s AND sekcja = %s ORDER BY id DESC LIMIT 10")
    cur.execute(q, (wybrana, sekcja))
    rows = cur.fetchall()
    print('---', sekcja, 'rows:', len(rows))
    for r in rows:
        print(r)

conn.close()
