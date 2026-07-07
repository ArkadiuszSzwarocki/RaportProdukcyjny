from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, order_ref, items, status FROM magazyn_dostawy WHERE items LIKE '%0062069047%' OR items LIKE '%SUR000001783408494927%'")
rows = cur.fetchall()
for r in rows:
    print(r['id'], r['order_ref'], r['status'])
    print(r['items'])
