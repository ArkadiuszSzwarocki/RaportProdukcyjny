#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdzenie wykonania (tonaz_rzeczywisty) vs planu (tonaz)
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'SPRAWDZENIE WYKONANIA vs PLAN - {today}')
print(f'{"="*100}\n')

# Sprawdź wszystkie plany
sekcje = ['Zasyp', 'Workowanie', 'Magazyn']

for sekcja in sekcje:
    print(f'\n{sekcja}:')
    print('-' * 100)
    
    cursor.execute('''
        SELECT 
            id, produkt, status, tonaz, tonaz_rzeczywisty
        FROM plan_produkcji
        WHERE sekcja = %s AND DATE(data_planu) = %s
        ORDER BY id
    ''', (sekcja, today))
    
    plany = cursor.fetchall()
    
    for p in plany:
        plan_val = p['tonaz'] if p['tonaz'] else 0
        real_val = p['tonaz_rzeczywisty'] if p['tonaz_rzeczywisty'] else 0
        diff = real_val - plan_val
        
        status_icon = '✅' if plan_val == real_val else '⚠️'
        
        print(f'  {status_icon} {p["produkt"]:20} | Plan: {plan_val:8.0f} kg | Rzecz: {real_val:8.0f} kg | Różnica: {diff:+8.0f} kg | status={p["status"]}')

print(f'\n{"="*100}\n')

cursor.close()
conn.close()
