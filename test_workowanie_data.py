from db import get_db_connection
from datetime import date

conn = get_db_connection()
c = conn.cursor()

# Query Workowanie plans (from Zasyp buffer)
c.execute("""
    SELECT id, produkt, status, real_start, real_stop 
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND status IN ('w toku', 'zakonczone')
    LIMIT 5
""", (date.today(),))

rows = c.fetchall()
print(f"Found {len(rows)} plans in Zasyp (w toku/zakonczone):")
for r in rows:
    plan_id, produkt, status, real_start, real_stop = r
    print(f"\nPlan {plan_id} ({produkt}): status={status}")
    print(f"  real_start={real_start} (type={type(real_start).__name__})")
    print(f"  real_stop={real_stop} (type={type(real_stop).__name__})")
    
    # Now test if this plan's paletki have data
    c.execute("""
        SELECT COUNT(*) FROM palety_workowanie WHERE plan_id = %s
    """, (plan_id,))
    pal_count = c.fetchone()[0]
    print(f"  Paletki in palety_workowanie: {pal_count}")

conn.close()
