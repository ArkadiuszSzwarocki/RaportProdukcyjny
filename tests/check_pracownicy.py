import sys,os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection
conn=get_db_connection()
cur=conn.cursor()
cur.execute('SELECT id, imie_nazwisko FROM pracownicy ORDER BY id DESC LIMIT 50')
rows=cur.fetchall()
for r in rows:
    print(r)
cur.close(); conn.close()
