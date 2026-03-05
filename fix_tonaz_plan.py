#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Naprawienie pola tonaz (plan) aby zgadzało się z tonaz_rzeczywisty (wykonanie)
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'NAPRAWA TONAZ (Plan) -> Wykonanie - {today}')
print(f'{"="*100}\n')

print('KROK 1: Pobranie aktualnych wartości...')
print('-' * 100)

cursor.execute('''
    SELECT 
        id, sekcja, produkt, tonaz, tonaz_rzeczywisty
    FROM plan_produkcji
    WHERE DATE(data_planu) = %s AND is_deleted = 0
    ORDER BY sekcja, produkt
''', (today,))

plany = cursor.fetchall()

do_naprawy = []
for p in plany:
    if p['tonaz'] != p['tonaz_rzeczywisty']:
        do_naprawy.append(p)
        print(f'  ⚠️  {p["sekcja"]:12} | {p["produkt"]:20} | id={p["id"]:4} | tonaz={p["tonaz"]:8.0f} -> {p["tonaz_rzeczywisty"]:8.0f}')

if not do_naprawy:
    print('  ✅ Wszystkie plany się zgadzają!')
    conn.close()
    exit(0)

print(f'\nRazem do naprawy: {len(do_naprawy)} planów\n')

# ===== NAPRAWA =====
print('KROK 2: Aktualizacja tonaz = tonaz_rzeczywisty...')
print('-' * 100)

naprawione = 0
for p in do_naprawy:
    cursor.execute('''
        UPDATE plan_produkcji
        SET tonaz = tonaz_rzeczywisty
        WHERE id = %s
    ''', (p['id'],))
    
    naprawione += 1
    print(f'  ✅ {p["sekcja"]:12} | {p["produkt"]:20} | updated')

conn.commit()

print(f'\nNaprawiono: {naprawione} planów\n')

# ===== WERYFIKACJA =====
print('KROK 3: Weryfikacja...')
print('-' * 100)

cursor.execute('''
    SELECT 
        id, sekcja, produkt, tonaz, tonaz_rzeczywisty
    FROM plan_produkcji
    WHERE DATE(data_planu) = %s AND is_deleted = 0
    ORDER BY sekcja, produkt
''', (today,))

plany_after = cursor.fetchall()

print('\nSTAN PO NAPRAWIE:')
for sekcja_name in ['Zasyp', 'Workowanie', 'Magazyn']:
    plany_sec = [p for p in plany_after if p['sekcja'] == sekcja_name]
    if plany_sec:
        print(f'\n{sekcja_name}:')
        for p in plany_sec:
            status = '✅' if p['tonaz'] == p['tonaz_rzeczywisty'] else '❌'
            print(f'  {status} {p["produkt"]:20} | tonaz={p["tonaz"]:8.0f} | rzecz={p["tonaz_rzeczywisty"]:8.0f}')

print(f'\n{"="*100}')
print('✅ NAPRAWA ZAKOŃCZONA')
print(f'{"="*100}\n')

cursor.close()
conn.close()
