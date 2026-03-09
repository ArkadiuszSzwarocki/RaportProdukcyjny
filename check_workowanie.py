from app.db import get_db_connection
conn = get_db_connection()
cur = conn.cursor(dictionary=True)

print('=== PLANY 10.03 ===')
cur.execute("""
    SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, zasyp_id 
    FROM plan_produkcji 
    WHERE DATE(data_planu)='2026-03-10' 
    ORDER BY sekcja, id
""")
for r in cur.fetchall(): print(r)

print()
print('=== BUFOR 10.03 ===')
cur.execute("""
    SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty, spakowano, kolejka, status 
    FROM bufor 
    WHERE DATE(data_planu)='2026-03-10'
""")
for r in cur.fetchall(): print(r)

print()
print('=== PLAN WORKOWANIE powiazany z zasyp_id=1428 ===')
cur.execute("""
    SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, zasyp_id 
    FROM plan_produkcji 
    WHERE zasyp_id=1428
""")
for r in cur.fetchall(): print(r)

print()
print('=== PLAN WORKOWANIE powiazany z zasyp_id=1430 ===')
cur.execute("""
    SELECT id, data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, status, zasyp_id 
    FROM plan_produkcji 
    WHERE zasyp_id=1430
""")
for r in cur.fetchall(): print(r)

conn.close()
