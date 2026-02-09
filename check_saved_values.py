from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdź do jakiego planu użytkownik wpisywał wartości
cursor.execute("""
    SELECT id, produkt, sekcja, uszkodzone_worki, status, data_planu
    FROM plan_produkcji 
    WHERE uszkodzone_worki > 0
    ORDER BY id DESC
    LIMIT 10
""")

rows = cursor.fetchall()
print("=" * 70)
print("PLANY Z USZKODZONYMI WORKKAMI (uszkodzone_worki > 0)")
print("=" * 70)

if rows:
    for r in rows:
        print(f"ID={r[0]:3} | sekcja={r[2]:15} | produkt={r[1]:20} | uszk={r[3]:3} | status={r[4]:12}")
else:
    print("✓ Brak żadnych planów z uszkodzonymi workami!")
    print("\nSpradzam WSZYSTKIE plany:")
    cursor.execute("""
        SELECT id, produkt, sekcja, uszkodzone_worki, status
        FROM plan_produkcji 
        ORDER BY id DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} plans")
    for r in rows:
        print(f"ID={r[0]:3} | sekcja={r[2]:15} | produkt={r[1]:20} | uszk={r[3]} | status={r[4]:12}")

conn.close()
