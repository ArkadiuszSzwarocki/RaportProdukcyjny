from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print('=== BUFOR 09.03-10.03 ===')
cur.execute("""
    SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty, spakowano, kolejka, status 
    FROM bufor 
    WHERE DATE(data_planu) IN ('2026-03-09','2026-03-10') 
    ORDER BY data_planu, kolejka
""")
for r in cur.fetchall():
    print(r)

print()
print('=== PLAN_PRODUKCJI FLEX MILCH ===')
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty 
    FROM plan_produkcji 
    WHERE produkt LIKE '%FLEX%' 
    ORDER BY data_planu, id
""")
for r in cur.fetchall():
    print(r)

print()
print('=== PLAN_PRODUKCJI 09.03-10.03 (wszystkie) ===')
cur.execute("""
    SELECT id, data_planu, produkt, sekcja, status, tonaz, tonaz_rzeczywisty 
    FROM plan_produkcji 
    WHERE DATE(data_planu) IN ('2026-03-09','2026-03-10')
    ORDER BY data_planu, id
""")
for r in cur.fetchall():
    print(r)

conn.close()
