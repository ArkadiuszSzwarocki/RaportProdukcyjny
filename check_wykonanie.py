#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdzenie pól wykonania w planach
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'SPRAWDZENIE WYKONANIA W PLANACH - {today}')
print(f'{"="*100}\n')

# Sprawdź wszystkie plany
sekcje = ['Zasyp', 'Workowanie', 'Magazyn']

for sekcja in sekcje:
    print(f'\n{sekcja}:')
    print('-' * 100)
    
    cursor.execute('''
        SELECT 
            id, produkt, status, tonaz, tonaz_rzeczywisty, wykonanie,
            (SELECT COUNT(*) FROM szarze WHERE plan_id = plan_produkcji.id) as ile_szarze,
            (SELECT SUM(waga) FROM szarze WHERE plan_id = plan_produkcji.id) as suma_szarze,
            (SELECT COUNT(*) FROM dosypki WHERE plan_id = plan_produkcji.id AND potwierdzone = 1) as ile_dosypki,
            (SELECT SUM(kg) FROM dosypki WHERE plan_id = plan_produkcji.id AND potwierdzone = 1) as suma_dosypki
        FROM plan_produkcji
        WHERE sekcja = %s AND DATE(data_planu) = %s
        ORDER BY id
    ''', (sekcja, today))
    
    plany = cursor.fetchall()
    
    for p in plany:
        print(f'  {p["produkt"]:20} | id={p["id"]:4} | status={p["status"]:12}')
        print(f'    Plan: {p["tonaz"]:6.0f} kg')
        print(f'    Rzecz: {p["tonaz_rzeczywisty"]:6.0f} kg')
        print(f'    Wykonanie: {p["wykonanie"] or "NULL":6}')
        
        if p['ile_szarze'] > 0:
            print(f'    Szarże: {p["ile_szarze"]} szt, suma={p["suma_szarze"]:.0f} kg')
        
        if p['ile_dosypki'] > 0:
            print(f'    Dosypki: {p["ile_dosypki"]} szt, suma={p["suma_dosypki"]:.0f} kg')
        
        # Sprawdź palety
        if sekcja == 'Workowanie':
            cursor.execute('''
                SELECT COUNT(*) as cnt, SUM(waga) as suma
                FROM palety_workowanie
                WHERE plan_id = %s
            ''', (p['id'],))
            palety = cursor.fetchone()
            if palety['cnt'] > 0:
                print(f'    Palety: {palety["cnt"]} szt, suma={palety["suma"]:.0f} kg')
        
        if sekcja == 'Magazyn':
            cursor.execute('''
                SELECT COUNT(*) as cnt, SUM(waga_netto) as suma
                FROM magazyn_palety
                WHERE plan_id = %s AND DATE(data_planu) = %s
            ''', (p['id'], today))
            mag_palety = cursor.fetchone()
            if mag_palety['cnt'] > 0:
                print(f'    Magazyn palety: {mag_palety["cnt"]} szt, suma={mag_palety["suma"]:.0f} kg')
        print()

print(f'{"="*100}\n')

cursor.close()
conn.close()
