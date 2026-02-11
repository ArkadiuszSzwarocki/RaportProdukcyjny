from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdzenie przed usunięciem
print("=== PRZED USUNIĘCIEM ===")
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
before = cursor.fetchone()[0]
print(f"BUF zlecenia: {before}")

# Usunięcie wszystkich naraz
print("\n=== USUWANIE ===")
cursor.execute("""
    DELETE FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
deleted = cursor.rowcount
print(f"Usunięto wierszy: {deleted}")
conn.commit()
print("COMMIT wykonany")

# Weryfikacja o usunięcia
print("\n=== PO USUNIĘCIU ===")
cursor.execute("""
    SELECT COUNT(*) FROM plan_produkcji 
    WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
""")
after = cursor.fetchone()[0]
print(f"BUF zlecenia: {after}")

if after == 0:
    print("✅ USUNIĘTE POMYŚLNIE")
else:
    print(f"❌ NADAL POZOSTAŁO: {after}")

conn.close()
