#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cofnięcie zmian - przywrócenie oryginalnych wartości tonaz
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'COFNIĘCIE ZMIAN - {today}')
print(f'{"="*100}\n')

# Przywróć oryginalne wartości tonaz na Zasyp
restore_map = {
    1364: 9000,      # MOM INSTANT Zasyp
    1366: 1000,      # MILK BAND BIAŁE Zasyp
    1368: 12000      # HOLENDER Zasyp
}

print('PRZYWRACANIE ORYGINALNYCH WARTOŚCI TONAZ:')
print('-' * 100)

for plan_id, orig_tonaz in restore_map.items():
    cursor.execute('''
        SELECT produkt, tonaz, tonaz_rzeczywisty, sekcja
        FROM plan_produkcji
        WHERE id = %s
    ''', (plan_id,))
    
    plan = cursor.fetchone()
    
    if plan:
        cursor.execute('''
            UPDATE plan_produkcji
            SET tonaz = %s
            WHERE id = %s
        ''', (orig_tonaz, plan_id))
        
        print(f'  ✅ {plan["sekcja"]:12} | {plan["produkt"]:20} | {plan["tonaz"]:.0f} -> {orig_tonaz:.0f} kg')

conn.commit()

# Dla Workowania przywróć też
print(f'\nWorkowanie (MOM INSTANT):')
cursor.execute('''
    UPDATE plan_produkcji
    SET tonaz = 1000
    WHERE id = 1365
''')
conn.commit()

cursor.execute('''
    SELECT produkt, tonaz FROM plan_produkcji WHERE id = 1365
''', ())
work = cursor.fetchone()
if work:
    print(f'  ✅ Workowanie    | {work["produkt"]:20} | 11206 -> 1000 kg')

print(f'\nCOFNIĘTO: 4 zmian')
print(f'{"="*100}\n')

cursor.close()
conn.close()
