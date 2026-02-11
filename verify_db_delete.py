import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print("=== WERYFIKACJA W BAZIE DANYCH ===\n")

# 1. Workowanie z _BUF
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
count = cursor.fetchone()[0]
print(f"Workowanie z '_BUF' w plan_produkcji: {count}")

# 2. Zasyp z _BUF
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Zasyp' AND nazwa_zlecenia LIKE '%_BUF%'
""")
count = cursor.fetchone()[0]
print(f"Zasyp z '_BUF' w plan_produkcji: {count}")

# 3. Wpisy w bufor
cursor.execute("""
    SELECT COUNT(*) FROM bufor WHERE status = 'aktywny'
""")
count = cursor.fetchone()[0]
print(f"Aktywne wpisy w bufor: {count}")

# 4. Szczegółowo co jest w bufor
cursor.execute("""
    SELECT id, produkt FROM bufor 
    WHERE status = 'aktywny'
    LIMIT 10
""")
rows = cursor.fetchall()
if rows:
    print(f"\nWpisy w bufor:")
    for row in rows:
        print(f"  - ID {row[0]}: {row[1]}")
else:
    print("\nBuf jest pusty")

# 5. Ile razem wszystkich plan_produkcji
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji
""")
total = cursor.fetchone()[0]
print(f"\nRazem all plan_produkcji: {total}")

conn.close()
print("\n✅ Weryfikacja ukończona")
