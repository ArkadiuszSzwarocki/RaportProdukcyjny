from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("""
SELECT id, produkt, zasyp_id, data_planu, tonaz_rzeczywisty, spakowano 
FROM bufor WHERE status = 'aktywny'
""")
bufor_active = cursor.fetchall()

cursor.execute("""
SELECT id, produkt, zasyp_id, data_planu, status 
FROM plan_produkcji WHERE sekcja = 'Workowanie' AND data_planu = '2026-03-31'
""")
workowanie_today = cursor.fetchall()
print("ACTIVE BUFOR:")
for b in bufor_active: print(b)
print("WORKOWANIE TODAY:")
for w in workowanie_today: print(w)
conn.close()
