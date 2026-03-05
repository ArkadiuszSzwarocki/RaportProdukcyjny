#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdzenie źródeł wartości wykonania
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print('DLACZEGO WYKONANIE - ŹRÓDŁA')
print(f'{"="*100}\n')

# Dla każdego produktu na Zasyp
for prod in ['MOM INSTANT', 'MILK BAND BIAŁE', 'HOLENDER']:
    print(f'{prod}:')
    
    # Plan id
    cursor.execute('''
        SELECT id, tonaz, tonaz_rzeczywisty FROM plan_produkcji
        WHERE sekcja='Zasyp' AND produkt=%s AND DATE(data_planu)=%s
    ''', (prod, today))
    p = cursor.fetchone()
    
    if p:
        plan_id = p['id']
        print(f'  Plan ID: {plan_id} | plan_tonaz={p["tonaz"]:.0f} | tonaz_rzeczywisty={p["tonaz_rzeczywisty"]:.0f}')
        
        # Szarże
        cursor.execute('''
            SELECT SUM(waga) as suma FROM szarze WHERE plan_id = %s
        ''', (plan_id,))
        s = cursor.fetchone()
        szarze_sum = s['suma'] or 0 if s else 0
        print(f'  Szarże: {szarze_sum:.0f} kg')
        
        # Dosypki
        cursor.execute('''
            SELECT SUM(kg) as suma FROM dosypki WHERE plan_id = %s AND potwierdzone = 1
        ''', (plan_id,))
        d = cursor.fetchone()
        dosypki_sum = d['suma'] or 0 if d else 0
        print(f'  Dosypki: {dosypki_sum:.0f} kg')
        
        razem = szarze_sum + dosypki_sum
        print(f'  Razem (szarże+dosypki): {razem:.0f} kg')
        print()

conn.close()
