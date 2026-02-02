from db import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
c = conn.cursor()

target_date = date(2026, 2, 2)
print(f"Checking plans for {target_date}:")

# Get ALL plans for that day
c.execute("""
    SELECT id, produkt, sekcja, status, real_start 
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s
    ORDER BY sekcja, id
""", (target_date,))

rows = c.fetchall()
print(f"\nTotal plans on {target_date}: {len(rows)}")

sekcje = {}
for r in rows:
    plan_id, produkt, sekcja, status, real_start = r
    if sekcja not in sekcje:
        sekcje[sekcja] = []
    sekcje[sekcja].append({
        'id': plan_id,
        'produkt': produkt,
        'status': status,
        'real_start': real_start
    })

for sekcja_name in sorted(sekcje.keys()):
    plans = sekcje[sekcja_name]
    print(f"\n{sekcja_name}: {len(plans)} plans")
    for p in plans[:3]:  # Show first 3
        print(f"  Plan {p['id']} ({p['produkt']}): status={p['status']}, real_start={p['real_start']}")

conn.close()
