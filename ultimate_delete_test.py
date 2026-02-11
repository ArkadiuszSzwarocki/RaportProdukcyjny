from app.db import get_db_connection

print("=== ULTIMATE DELETE TEST ===\n")

# Get actual connection that app uses
conn = get_db_connection()
cursor = conn.cursor()

print("1. Checking current count before DELETE...")
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
before = cursor.fetchone()[0]
print(f"   Before: {before} rows")

# Get the IDs
cursor.execute("""
    SELECT id FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    LIMIT 5
""")
sample_ids = [row[0] for row in cursor.fetchall()]
print(f"   Sample IDs: {sample_ids}")

print("\n2. Executing DELETE...")
cursor.execute("""
    DELETE FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
deleted = cursor.rowcount
print(f"   Rowcount returned: {deleted}")

print("\n3. Committing...")
conn.commit()
print("   Commit done")

print("\n4. Checking after DELETE (same connection)...")
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
after_same_conn = cursor.fetchone()[0]
print(f"   After (same cursor): {after_same_conn} rows")

print("\n5. Closing and reconnecting...")
conn.close()

# New connection
conn2 = get_db_connection()
cursor2 = conn2.cursor()

cursor2.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
after_new_conn = cursor2.fetchone()[0]
print(f"   After (new conn): {after_new_conn} rows")

if after_new_conn == 0:
    print("\n✅ SUCCESS - ALL DELETED!")
else:
    # Try to find what's left
    cursor2.execute("""
        SELECT id, produkt, nazwa_zlecenia FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
        LIMIT 3
    """)
    remaining = cursor2.fetchall()
    print(f"\n❌ STILL {after_new_conn} rows remaining:")
    for row in remaining:
        print(f"   ID {row[0]}: {row[1]} | {row[2]}")

conn2.close()
