from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("DIAGNOZA - PLAN 890 (10000 kg AGRO MILK TOP)")
print("=" * 80)

# Plan 890
print("\n1. STATUS PLANU 890:")
cursor.execute('''
    SELECT id, produkt, tonaz, status, data_planu 
    FROM plan_produkcji WHERE id = 890
''')
result = cursor.fetchone()
if result:
    print(f"   ID: {result[0]}")
    print(f"   Produkt: {result[1]}")
    print(f"   Plan tonaz: {result[2]} kg")
    print(f"   Status: {result[3]}")
    print(f"   Data planu: {result[4]}")

# Szarze dla planu 890
print("\n2. SZARZE DLA PLANU 890:")
cursor.execute('''
    SELECT id, waga, status, data_dodania 
    FROM szarze WHERE plan_id = 890 
    ORDER BY id
''')
results = cursor.fetchall()
szarze_total = 0
for r in results:
    szarze_total += r[1]
    print(f"   ID {r[0]}: {r[1]} kg | Status: {r[2]} | Data: {r[3]}")
print(f"   RAZEM SZARZE: {szarze_total} kg")

# Workowanie dla planu 890
print("\n3. WORKOWANIE DLA PLANU 890:")
cursor.execute('''
    SELECT id, waga, status, data_dodania 
    FROM palety_workowanie WHERE plan_id = 890 
    ORDER BY id
''')
results = cursor.fetchall()
work_total = 0
if results:
    for r in results:
        work_total += r[1]
        print(f"   ID {r[0]}: {r[1]} kg | Status: {r[2]} | Data: {r[3]}")
    print(f"   RAZEM WORKOWANIE: {work_total} kg")
else:
    print("   ✗ BRAK WORKOWANIA")

# Bufor dla szarze plan 890
print("\n4. BUFOR DLA PLANU 890 (z szarze):")
cursor.execute('''
    SELECT b.id, b.produkt, b.tonaz_rzeczywisty, b.status
    FROM bufor b
    WHERE b.zasyp_id IN (SELECT id FROM szarze WHERE plan_id = 890)
    ORDER BY b.id
''')
results = cursor.fetchall()
if results:
    for r in results:
        print(f"   ID {r[0]}: {r[1]} | {r[2]} kg | Status: {r[3]}")
else:
    print("   ✗ BRAK BUFORA")

print("\n" + "=" * 80)
print("PODSUMOWANIE:")
print("=" * 80)
print(f"Plan 890: {szarze_total} kg szarze vs {work_total} kg workowanie")
if szarze_total > work_total:
    diff = szarze_total - work_total
    print(f"⚠️  RESZTA W BUFORZE: {diff} kg")

cursor.close()
conn.close()
