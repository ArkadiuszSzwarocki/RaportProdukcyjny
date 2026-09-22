import json
from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print("=== RECENT 20 PALLETS FROM palety_workowanie (PSD) ===")
cur.execute("SELECT * FROM palety_workowanie ORDER BY id DESC LIMIT 20")
for r in cur.fetchall():
    print(r)

print("\n=== RECENT 10 DELIVERIES (magazyn_dostawy) ===")
cur.execute("SELECT * FROM magazyn_dostawy ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(r.get('id'), r.get('typ_dokumentu'), r.get('nr_dokumentu'), r.get('supplier'), r.get('status'), r.get('created_at'))
    items = r.get('items')
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except:
            pass
    print("  items:", items)

conn.close()
