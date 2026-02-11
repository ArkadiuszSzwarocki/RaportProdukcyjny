from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check plan_produkcji
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
result = cursor.fetchone()
print(f"plan_produkcji z '_BUF': {result[0] if result else 0}")

# Check bufor table
cursor.execute("""
    SELECT COUNT(*) FROM bufor 
    WHERE status = 'aktywny'
""")
result = cursor.fetchone()
print(f"Aktywne wpisy w bufor: {result[0] if result else 0}")

# Also list them
cursor.execute("""
    SELECT id, produkt, nazwa_zlecenia, status FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
    LIMIT 5
""")
rows = cursor.fetchall()
if rows:
    print(f"\nNajadal istnieją w plan_produkcji:")
    for row in rows:
        print(f"  ID {row[0]}: {row[1]} | {row[2]} | {row[3]}")
else:
    print("\n✅ Brak BUF zleceń w plan_produkcji")

conn.close()
