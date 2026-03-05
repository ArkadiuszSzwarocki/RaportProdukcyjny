#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Sprawdź rekordy Brak dosypki
cursor.execute('''
    SELECT id, plan_id, szarza_id, nazwa, kg, potwierdzone, data_zlecenia
    FROM dosypki 
    WHERE nazwa LIKE '%Brak%'
    ORDER BY id DESC
    LIMIT 5
''')
rekordy = cursor.fetchall()
print('Rekordy "Brak dosypki":')
for r in rekordy:
    print(f'  ID={r["id"]} plan_id={r["plan_id"]} szarza_id={r["szarza_id"]} nazwa={r["nazwa"]} kg={r["kg"]} potw={r["potwierdzone"]}')

# Sprawdź czy plan_id 1374 ma jakieś szarże
print('\nSzarże dla planu 1374:')
cursor.execute('SELECT id, waga FROM szarze WHERE plan_id=1374 ORDER BY id DESC LIMIT 3')
szarze = cursor.fetchall()
for s in szarze:
    print(f'  ID={s["id"]} waga={s["waga"]}')

conn.close()
