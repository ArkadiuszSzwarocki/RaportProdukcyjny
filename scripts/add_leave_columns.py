import sys, os
sys.path.insert(0, os.path.abspath('.'))
from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

stmts = [
    "ALTER TABLE pracownicy ADD COLUMN urlop_biezacy INT DEFAULT 0",
    "ALTER TABLE pracownicy ADD COLUMN urlop_zalegly INT DEFAULT 0",
]

for s in stmts:
    try:
        cursor.execute(s)
        print('Executed:', s)
    except Exception as e:
        print('Skipped / error for:', s, '-', e)

conn.commit()
cursor.close()
conn.close()
print('Done')
