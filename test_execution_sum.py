from db import get_db_connection
from datetime import date

conn = get_db_connection()
c = conn.cursor()

target_date = date(2026, 2, 3)  # Today
print(f"Checking Workowanie execution for {target_date}:\n")

# Get plans from Workowanie sekcja
c.execute("""
    SELECT id, produkt, tonaz_rzeczywisty
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
    ORDER BY id
""", (target_date,))

plans = c.fetchall()
print(f"Plans in Workowanie sekcja: {len(plans)}")
total_plan_wykonanie = 0

for plan_id, produkt, tonaz_rzeczywisty in plans:
    print(f"  Plan {plan_id} ({produkt}): tonaz_rzeczywisty={tonaz_rzeczywisty}")
    if tonaz_rzeczywisty:
        total_plan_wykonanie += tonaz_rzeczywisty

print(f"\nTotal from plan_produkcji (tonaz_rzeczywisty): {total_plan_wykonanie}")

# Now check paletki_workowanie
c.execute("""
    SELECT SUM(waga) 
    FROM palety_workowanie
    WHERE DATE(data_dodania) = %s
""", (target_date,))

palety_sum = c.fetchone()[0] or 0
print(f"Total from palety_workowanie (waga): {palety_sum}")

# Check if there are paletki for Workowanie plans
c.execute("""
    SELECT plan_id, COUNT(*) as count, SUM(waga) as total_waga
    FROM palety_workowanie
    WHERE DATE(data_dodania) = %s
    GROUP BY plan_id
    ORDER BY plan_id
""", (target_date,))

rows = c.fetchall()
print(f"\nPaletki by plan:")
grand_total = 0
for plan_id, count, total_waga in rows:
    print(f"  Plan {plan_id}: {count} paletki, {total_waga} kg")
    grand_total += total_waga

print(f"\nGrand total paletki waga: {grand_total}")

conn.close()
