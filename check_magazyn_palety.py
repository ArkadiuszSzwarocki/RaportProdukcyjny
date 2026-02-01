#!/usr/bin/env python
# -*- coding: utf-8 -*-
from db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = str(date.today())

# Check all palety for today
cursor.execute('''
    SELECT pw.id, pw.plan_id, pw.waga, pw.status, p.sekcja, p.produkt
    FROM palety_workowanie pw
    JOIN plan_produkcji p ON pw.plan_id = p.id
    WHERE DATE(pw.data_dodania) = %s
    ORDER BY pw.id DESC
''', (today,))
palety = cursor.fetchall()
print(f'Palety w bazie dla dzisiaj ({today}):')
if palety:
    for p in palety:
        print(f'  ID={p[0]}, plan_id={p[1]}, waga={p[2]}, status={p[3]}, sekcja={p[4]}, produkt={p[5]}')
else:
    print("  (brak palet)")

conn.close()
