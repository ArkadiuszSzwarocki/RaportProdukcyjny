import mysql.connector
import sys
import re
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("""
    SELECT w.id as work_id, w.produkt, w.tonaz_rzeczywisty as w_kg, 
           z.id as zasyp_id, z.tonaz_rzeczywisty as z_kg,
           w.nazwa_zlecenia, w.typ_produkcji
    FROM plan_produkcji_agro w
    LEFT JOIN plan_produkcji_agro z ON w.zasyp_id = z.id
    WHERE w.id = 72
""")
p = cursor.fetchone()
print(f"p: {p}")

cursor.execute("""
    SELECT id, opakowanie_nazwa, stan_przed, wyprodukowano_szt, szt_na_palecie, zuzyte_worki, stan_po, autor_login, created_at
    FROM agro_workowanie_rozliczenie
    WHERE plan_id = %s
    ORDER BY created_at ASC
""", (p['work_id'],))
rozliczenia = cursor.fetchall()
print(f"rozliczenia length: {len(rozliczenia)}")

bag_kg = 25.0
typ_prod = p.get('typ_produkcji') or ''
print(f"typ_prod value: {repr(typ_prod)}")
kg_match = re.search(r'(\d+)', typ_prod)
if kg_match:
    bag_kg = float(kg_match.group(1))
    print(f"Matched kg from typ_prod: {bag_kg}")
else:
    print("No kg matched from typ_prod")
    if rozliczenia and len(rozliczenia) > 0:
        cursor.execute("SELECT kg_na_worek FROM agro_workowanie_rozliczenie WHERE plan_id = %s AND kg_na_worek IS NOT NULL LIMIT 1", (p['work_id'],))
        rw = cursor.fetchone()
        if rw and rw.get('kg_na_worek'):
            bag_kg = float(rw['kg_na_worek'])
            print(f"Fallback to first packaging record kg_na_worek: {bag_kg}")
    else:
        produkt_nazwa = str(p.get('produkt') or '').lower()
        if 'mleko' in produkt_nazwa or '20' in produkt_nazwa:
            bag_kg = 20.0
            print(f"Fallback based on product name: {bag_kg}")

print(f"Final bag_kg: {bag_kg}")
conn.close()
