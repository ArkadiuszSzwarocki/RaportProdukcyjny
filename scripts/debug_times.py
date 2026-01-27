import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection
from datetime import date

conn = get_db_connection()
cur = conn.cursor()
q = ("SELECT d.id, p.imie_nazwisko, d.problem, TIME_FORMAT(d.czas_start, '%H:%i'), "
     "TIME_FORMAT(d.czas_stop, '%H:%i') "
     "FROM dziennik_zmiany d LEFT JOIN pracownicy p ON d.pracownik_id = p.id "
     "ORDER BY d.id DESC LIMIT 20")
cur.execute(q)
rows = cur.fetchall()
if not rows:
    print('No rows found in dziennik_zmiany')
else:
    for r in rows:
        print(r)
conn.close()
