from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT instance_id, component, status, started_at, last_heartbeat, extra FROM app_instance_heartbeat')
rows = cur.fetchall()
for r in rows:
    print(r)
