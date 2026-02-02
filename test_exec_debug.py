from db import get_db_connection
from datetime import date

conn = get_db_connection()
c = conn.cursor()

target_date = date(2026, 2, 2)
print(f"Checking Workowanie execution for {target_date}:\n")

# Get paletki
c.execute("""
    SELECT plan_id, COUNT(*) as count, SUM(waga) as total_waga
    FROM palety_workowanie
    WHERE DATE(data_dodania) = %s
    GROUP BY plan_id
    ORDER BY plan_id
""", (target_date,))

rows = c.fetchall()
print(f"Paletki by plan:")
grand_total = 0
for plan_id, count, total_waga in rows:
    print(f"  Plan {plan_id}: {count} paletki, {total_waga} kg")
    grand_total += total_waga

print(f"\nTotal paletki: {grand_total} kg")

# Check co QueryHelper zwraca
from utils.queries import QueryHelper
paletki = QueryHelper.get_paletki_for_plan(403)  # Plan 403
print(f"\nQueryHelper.get_paletki_for_plan(403): {len(paletki)} rows")
total_waga_qh = sum(r[2] for r in paletki if len(r) > 2)
print(f"Sum of waga: {total_waga_qh}")

conn.close()
