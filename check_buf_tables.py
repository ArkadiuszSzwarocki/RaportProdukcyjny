from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check Zasyp with _BUF
cursor.execute("""
    SELECT id, produkt, nazwa_zlecenia, status FROM plan_produkcji 
    WHERE sekcja = 'Zasyp' AND nazwa_zlecenia LIKE '%_BUF%'
""")
zasypy = cursor.fetchall()
print(f"Zasyp z '_BUF': {len(zasypy)}")
for row in zasypy:
    print(f"  ID {row[0]}: {row[1]} | {row[2]} | {row[3]}")

# Check Workowanie with _BUF
cursor.execute("""
    SELECT id, produkt, nazwa_zlecenia, status FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
work = cursor.fetchall()
print(f"\nWorkowanie z '_BUF': {len(work)}")

# Check bufor table
cursor.execute("""
    SELECT COUNT(*) FROM bufor 
    WHERE status = 'aktywny'
""")
buf = cursor.fetchone()[0]
print(f"Wpisy w bufor: {buf}")

conn.close()
