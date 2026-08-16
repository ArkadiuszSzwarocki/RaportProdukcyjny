from app.db import get_db_connection
try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute('SELECT * FROM palety_agro WHERE plan_id = 125')
    print('Palety w palety_agro:', cur.fetchall())
    
    cur.execute('SELECT * FROM palety_workowanie WHERE plan_id = 125')
    print('Palety w palety_workowanie:', cur.fetchall())
except Exception as e:
    print('Blad:', e)

