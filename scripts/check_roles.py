from db import get_db_connection
conn = None
try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name, label FROM roles ORDER BY id ASC')
    rows = cur.fetchall()
    print('ROLES:', rows)
except Exception as e:
    print('ERROR:', e)
finally:
    if conn:
        try: conn.close()
        except: pass
