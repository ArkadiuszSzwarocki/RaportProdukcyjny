from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute('SHOW TRIGGERS')
triggers = cur.fetchall()
for t in triggers:
    print(t['Trigger'], 'on', t['Table'])
