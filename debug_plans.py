from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check szarża for plans 513 and 515 (all time, not just today)
cursor.execute("""
    SELECT id, plan_id, status, DATE(data_dodania)
    FROM szarze
    WHERE plan_id IN (513, 515)
    ORDER BY id DESC
    LIMIT 20
""")

szarze = cursor.fetchall()
print(f"=== SZARŻA FOR PLANS 513/515 (ALL TIME) ===")
if szarze:
    for s in szarze:
        print(f"  ID {s[0]}: plan_id={s[1]}, status={s[2]}, data={s[3]}")
else:
    print("  Brak szarży!")

# Check plans 513/515 details
print()
cursor.execute("""
    SELECT id, produkt, tonaz, status, sekcja, DATE(data_planu), tonaz_rzeczywisty
    FROM plan_produkcji
    WHERE id IN (513, 515)
""")

plans = cursor.fetchall()
print(f"=== PLANS 513/515 ===")
for p in plans:
    print(f"  ID {p[0]}: {p[1]} | sekcja={p[4]} | status={p[3]} | data={p[5]} | rzeczywisty={p[6]}")

# What about plan 460? Does it exist at all?
print()
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji WHERE id = 460
""")
exists = cursor.fetchone()[0]
print(f"Plan 460 exists: {exists == 1}")

cursor.close()
conn.close()
