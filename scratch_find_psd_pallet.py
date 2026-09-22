import json
from app.core.database import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

search_terms = ["178721629555", "PSD00000178721629555", "17872162", "721629555", "1787216"]

tables_to_check = [
    "palety_workowanie",
    "magazyn_palety",
    "magazyn_dostawy",
    "palety_historia",
    "magazyn_ruch",
    "magazyn_ruchy_unified",
    "print_jobs",
    "bufor",
    "plan_produkcji"
]

print("=== SEARCHING TABLES ===")
for t in tables_to_check:
    cur.execute(f"DESCRIBE `{t}`")
    cols = [c['Field'] for c in cur.fetchall()]
    for col in cols:
        for term in search_terms:
            try:
                cur.execute(f"SELECT * FROM `{t}` WHERE `{col}` LIKE %s LIMIT 10", (f"%{term}%",))
                res = cur.fetchall()
                if res:
                    print(f"\n[FOUND IN {t}.{col} for '{term}': {len(res)} rows]")
                    for r in res:
                        print(r)
            except Exception as e:
                pass

print("\n=== RECENT 10 PALLETS IN palety_workowanie ===")
cur.execute("SELECT * FROM palety_workowanie ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(r)

print("\n=== RECENT 10 PALLETS IN magazyn_palety ===")
cur.execute("SELECT * FROM magazyn_palety ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(r)

print("\n=== RECENT 10 ORDERS IN magazyn_dostawy ===")
cur.execute("SELECT id, typ_dokumentu, nr_dokumentu, status, created_at, items FROM magazyn_dostawy ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    items = r['items']
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except:
            pass
    r['items'] = items
    print(r)

conn.close()
