#!/usr/bin/env python
"""Check plan 1262 status and completeness"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Find plan 1262
cursor.execute('SELECT id, produkt, data_planu, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE id = 1262')
plan = cursor.fetchone()

if plan:
    print('Plan 1262:')
    for key, val in plan.items():
        print(f'  {key}: {val}')
else:
    print('Plan 1262 nie znaleziony')

# Find any plan na 04.03 z incomplete work
cursor.execute('''SELECT id, sekcja, produkt, data_planu, tonaz, tonaz_rzeczywisty, status 
FROM plan_produkcji 
WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'zasyp'
ORDER BY id''', ('2026-03-04',))

plans = cursor.fetchall()
print(f'\nWszystkie plany Zasyp na 04.03: {len(plans)} znalezione')
for p in plans:
    incomplete = '❌ NIEZUPEŁNY' if (p['tonaz_rzeczywisty'] or 0) < p['tonaz'] else '✅ PEŁNY'
    print(f"  ID={p['id']}, {p['sekcja']}, {p['produkt']}, status={p['status']}, plan={p['tonaz']}, rzeczywisty={p['tonaz_rzeczywisty']} {incomplete}")

cursor.close()
conn.close()
