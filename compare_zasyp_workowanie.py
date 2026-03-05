#!/usr/bin/env python
"""Porównanie planów Workowania z realizacją Zasypu"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()
print(f'\n{"="*80}')
print(f'PORÓWNANIE: Plan Workowanie vs Realizacja Zasypu ({today})')
print(f'{"="*80}\n')

# Pobierz dane Zasypu
cursor.execute('''
    SELECT produkt, tonaz as tonaz_plan, tonaz_rzeczywisty
    FROM plan_produkcji 
    WHERE sekcja='Zasyp' AND DATE(data_planu)=%s
    ORDER BY produkt
''', (today,))
zasypy = {row['produkt']: row for row in cursor.fetchall()}

# Pobierz dane Workowania
cursor.execute('''
    SELECT id, produkt, tonaz as tonaz_plan, tonaz_rzeczywisty, status
    FROM plan_produkcji 
    WHERE sekcja='Workowanie' AND DATE(data_planu)=%s
    ORDER BY produkt
''', (today,))
pracy = cursor.fetchall()

print('PRODUKTY:')
for w in pracy:
    prod = w['produkt']
    z = zasypy.get(prod)
    if z:
        w_plan = w['tonaz_plan']
        z_real = z['tonaz_rzeczywisty']
        status = '✓' if w_plan == z_real else '✗'
        print(f'{status} {prod:20} | Workowanie={w_plan:8.0f} | Zasyp_real={z_real:8.0f} | Workowanie_status={w["status"]}')
    else:
        print(f'✗ {prod:20} | BRAK NA ZASYP!')

conn.close()
print(f'\n{"="*80}\n')
