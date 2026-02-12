from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("PLAN 882 - BIEŻĄCY STAN")
print("=" * 80)

# Plan 882
cursor.execute('SELECT id, produkt, tonaz, status FROM plan_produkcji WHERE id = 882')
plan = cursor.fetchone()
if plan:
    print(f"Plan 882: {plan[1]} | Tonaz: {plan[2]} kg | Status: {plan[3]}")

# Szarze dla planu 882
cursor.execute('SELECT id, waga, status FROM szarze WHERE plan_id = 882')
szarze_list = cursor.fetchall()
print(f"\nSzarze (plan 882): {len(szarze_list)} entry/entries")
for szarze in szarze_list:
    print(f"  - ID {szarze[0]}: {szarze[1]} kg | Status: {szarze[2]}")

# Workowanie dla planu 882
cursor.execute('SELECT id, waga, tara, status FROM palety_workowanie WHERE plan_id = 882')
palet = cursor.fetchall()
print(f"\nPalety Workowanie (plan 882): {len(palet)} palet/palety")
total_workowanie = 0
for p in palet:
    print(f"  - ID {p[0]}: Waga: {p[1]} kg | Tara: {p[2]} kg | Status: {p[3]}")
    if p[1]:
        total_workowanie += p[1]
print(f"  RAZEM Workowanie: {total_workowanie} kg")

# Bufor dla planu 882
cursor.execute('SELECT id, produkt, tonaz_rzeczywisty, status FROM bufor WHERE zasyp_id IN (SELECT id FROM szarze WHERE plan_id = 882)')
buf = cursor.fetchall()
print(f"\nBuffer (plan 882): {len(buf)} entry/entries")
for b in buf:
    print(f"  - ID {b[0]}: {b[1]} | Tonaz: {b[2]} kg | Status: {b[3]}")

print("\n" + "=" * 80)
print("PLANY 625 i 890 - DLA PORÓWNANIA")
print("=" * 80)

for pid in [625, 890]:
    cursor.execute('SELECT id, produkt, tonaz, status FROM plan_produkcji WHERE id = %s', (pid,))
    plan = cursor.fetchone()
    if plan:
        print(f"\nPlan {pid}: {plan[1]} | Tonaz: {plan[2]} kg | Status: {plan[3]}")
        
        cursor.execute('SELECT SUM(waga) FROM szarze WHERE plan_id = %s', (pid,))
        szarze_sum = cursor.fetchone()[0] or 0
        print(f"  Szarze suma: {szarze_sum} kg")
        
        cursor.execute('SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s', (pid,))
        palet_sum = cursor.fetchone()[0] or 0
        print(f"  Workowanie suma: {palet_sum} kg")

cursor.close()
conn.close()
