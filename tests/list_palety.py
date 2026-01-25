import sys, os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection
conn = get_db_connection()
c = conn.cursor()
c.execute("SELECT id, plan_id, waga, status, data_dodania FROM palety_workowanie ORDER BY id DESC LIMIT 20")
rows = c.fetchall()
print('PALETY:')
for r in rows:
    print(r)

c.close()
conn.close()
