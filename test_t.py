from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, items FROM magazyn_dostawy WHERE status = 'OCZEKUJE'")
transfers = cur.fetchall()
found = False
for t in transfers:
    items = t.get('items')
    if items and 'SUR080520268243385213' in items:
        print(f"Found in transfer {t['id']}")
        found = True
if not found:
    print('Not found in any pending transfer')
