#!/usr/bin/env python
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Sprawdź ostatnie rekordy dosypki
cursor.execute('''
    SELECT id, plan_id, nazwa, kg, data_zlecenia, potwierdzone
    FROM dosypki 
    ORDER BY id DESC 
    LIMIT 10
''')
rekordy = cursor.fetchall()
print('Ostatnie 10 rekordów dosypki:')
for r in rekordy:
    print(f'  ID={r["id"]:3} plan_id={r["plan_id"]:4} nazwa={r["nazwa"]:20} kg={r["kg"]:7.2f} data={r["data_zlecenia"]} potw={r["potwierdzone"]}')

# Sprawdź czy są rekordy z "Brak dosypki"
cursor.execute('''
    SELECT id, plan_id, nazwa, kg, data_zlecenia, potwierdzone
    FROM dosypki 
    WHERE nazwa LIKE '%Brak%' OR nazwa LIKE '%brak%'
    ORDER BY id DESC
''')
brak = cursor.fetchall()
print(f'\nRekordy z "Brak dosypki": {len(brak)}')
for r in brak:
    print(f'  ID={r["id"]:3} plan_id={r["plan_id"]:4} nazwa={r["nazwa"]:20} kg={r["kg"]:7.2f}')

conn.close()
