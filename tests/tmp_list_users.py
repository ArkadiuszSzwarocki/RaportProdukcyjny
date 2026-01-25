import sys, os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection

conn = get_db_connection()
c = conn.cursor()
try:
    c.execute("SELECT id, login, pracownik_id, rola FROM uzytkownicy LIMIT 20")
except Exception as e:
    print('SELECT1 failed:', e)
    c.execute("SELECT * FROM uzytkownicy LIMIT 5")
cols = [d[0] for d in c.description]
rows = c.fetchall()
print('COLS:', cols)
for r in rows:
    print(r)

c.close()
conn.close()
