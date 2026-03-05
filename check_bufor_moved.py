#!/usr/bin/env python
"""Check if buffer data moved successfully"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Check buffer on 04.03
cursor.execute('SELECT * FROM bufor WHERE DATE(data_planu) = %s LIMIT 1', ('2026-03-04',))
rows_04 = cursor.fetchall()
print('=== BUFOR NA 04.03 ===')
if rows_04:
    for row in rows_04:
        print(f"  {row}")
else:
    print('  (brak zapisów)')

# Check buffer on 05.03
cursor.execute('SELECT * FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-05',))
rows_05 = cursor.fetchall()
print('=== BUFOR NA 05.03 ===')
if rows_05:
    for row in rows_05:
        print(f"  {row}")
else:
    print('  (brak zapisów)')

# Check if plan 1287, 1288 were created
cursor.execute('SELECT id, produkt, data, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE id IN (1287, 1288)')
new_plans = cursor.fetchall()
print('=== NOWE PLANY 1287, 1288 ===')
if new_plans:
    for plan in new_plans:
        print(f"  ID={plan['id']}, Produkt={plan['produkt']}, data={plan['data']}, plan={plan['tonaz']}, rzeczywisty={plan['tonaz_rzeczywisty']}")
else:
    print('  (brak)')

cursor.close()
conn.close()
