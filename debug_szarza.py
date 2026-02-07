from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check szarża for these products
cursor.execute("""
    SELECT id, plan_id, status, DATE(data_dodania), 
           (SELECT produkt FROM plan_produkcji WHERE id = s.plan_id) as produkt
    FROM szarze s
    WHERE DATE(data_dodania) = CURDATE()
    ORDER BY id DESC
    LIMIT 10
""")

szarze = cursor.fetchall()
print(f"=== SZARŻA TODAY ===")
if szarze:
    for s in szarze:
        print(f"  ID {s[0]}: plan_id={s[1]}, status={s[2]}, produkt={s[4]}")
else:
    print("  Brak szarży!")

# Check if szarża has ze status 'zarejestowana'
print()
cursor.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN status = 'zarejestowana' THEN 1 END) as zarejestowana
    FROM szarze
    WHERE DATE(data_dodania) = CURDATE()
""")
counts = cursor.fetchone()
print(f"Szarża total: {counts[0]}")
print(f"Szarża zarejestowana: {counts[1]}")

# Check what status are in szarże
print()
cursor.execute("""
    SELECT DISTINCT status, COUNT(*) as cnt
    FROM szarze
    WHERE DATE(data_dodania) = CURDATE()
    GROUP BY status
""")
statuses = cursor.fetchall()
print(f"Statuses in szarże today:")
for s in statuses:
    print(f"  {s[0]}: {s[1]} records")

cursor.close()
conn.close()
