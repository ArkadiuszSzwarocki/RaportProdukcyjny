from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("=" * 80)
print("DEBUGOWANIE - SPRAWDZENIE ZMIAN W BAZIE")
print("=" * 80)

# Szarze 882 (ID 225)
print("\n1. SZARZE ID 225 (Plan 882):")
cursor.execute('SELECT id, plan_id, waga, status FROM szarze WHERE id = 225')
result = cursor.fetchone()
if result:
    print(f"   ✓ ZNALEZIONO: ID {result[0]} | Plan {result[1]} | Waga: {result[2]} kg | Status: {result[3]}")
else:
    print("   ✗ NIE ZNALEZIONO!")

# Workowanie dla 882
print("\n2. WORKOWANIE PLAN 882:")
cursor.execute('SELECT id, plan_id, waga, status FROM palety_workowanie WHERE plan_id = 882 ORDER BY id')
results = cursor.fetchall()
if results:
    print(f"   ✓ ZNALEZIONO {len(results)} entry/entries:")
    for r in results:
        print(f"      ID {r[0]} | Waga: {r[1]} kg | Status: {r[3]}")
else:
    print("   ✗ NIE ZNALEZIONO!")

# Workowanie dla 625
print("\n3. WORKOWANIE PLAN 625:")
cursor.execute('SELECT id, plan_id, waga, status FROM palety_workowanie WHERE plan_id = 625 ORDER BY id DESC LIMIT 5')
results = cursor.fetchall()
if results:
    print(f"   ✓ ZNALEZIONO (ostatnie 5):")
    for r in results:
        print(f"      ID {r[0]} | Waga: {r[1]} kg | Status: {r[3]}")
else:
    print("   ✗ NIE ZNALEZIONO!")

# Workowanie dla 890
print("\n4. WORKOWANIE PLAN 890:")
cursor.execute('SELECT id, plan_id, waga, status FROM palety_workowanie WHERE plan_id = 890 ORDER BY id DESC LIMIT 5')
results = cursor.fetchall()
if results:
    print(f"   ✓ ZNALEZIONO (ostatnie 5):")
    for r in results:
        print(f"      ID {r[0]} | Waga: {r[1]} kg | Status: {r[3]}")
else:
    print("   ✗ NIE ZNALEZIONO!")

print("\n" + "=" * 80)

cursor.close()
conn.close()
