#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Dodanie brakujących produktów do bufora
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'DODAWANIE PRODUKTÓW DO BUFORA - {today}')
print(f'{"="*100}\n')

# Mapowanie plan_id Zasyp dla każdego produktu
produkty_map = {
    'MOM INSTANT': 1364,
    'MILK BAND BIAŁE': 1366,
    'HOLENDER': 1368
}

print('KROK 1: Pobieranie danych produktów z Zasyp...')
print('-' * 100)

# Pobierz info o każdym produkcie z Zasyp
produkty_info = {}
for nazwa, plan_id in produkty_map.items():
    cursor.execute('''
        SELECT 
            id, produkt, tonaz_rzeczywisty, status
        FROM plan_produkcji
        WHERE id = %s AND sekcja = 'Zasyp'
    ''', (plan_id,))
    
    zasyp = cursor.fetchone()
    if zasyp:
        produkty_info[nazwa] = {
            'plan_id': plan_id,
            'tonaz': zasyp['tonaz_rzeczywisty'],
            'status': zasyp['status']
        }
        print(f'  ✅ {nazwa:20} | plan_id={plan_id} | tonaz={zasyp["tonaz_rzeczywisty"]:.0f} kg | status={zasyp["status"]}')
    else:
        print(f'  ❌ {nazwa:20} | plan_id={plan_id} - BIEŻacy brak!')

# Ustal kolejność w buforze
print(f'\nKROK 2: Ustalanie kolejności w buforze...')
print('-' * 100)

cursor.execute('''
    SELECT MAX(kolejka) as max_q FROM bufor 
    WHERE DATE(data_planu) = %s
''', (today,))
max_q = cursor.fetchone()
next_queue = (max_q['max_q'] or 0) + 1 if max_q else 1

print(f'  Następna kolejka: {next_queue}')

# Dodaj do bufora
print(f'\nKROK 3: Dodawanie produktów do bufora...')
print('-' * 100)

dodane = 0
for nazwa, info in produkty_info.items():
    cursor.execute('''
        INSERT INTO bufor 
        (data_planu, zasyp_id, produkt, tonaz_rzeczywisty, spakowano, kolejka, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    ''', (today, info['plan_id'], nazwa, info['tonaz'], 0, next_queue + dodane, 'aktywny'))
    
    print(f'  ✅ {nazwa:20} | kol={next_queue + dodane} | tonaz={info["tonaz"]:.0f} kg')
    dodane += 1

conn.commit()
print(f'\nDodano: {dodane} produkty')

# Weryfikacja
print(f'\n{"="*100}')
print('KROK 4: Weryfikacja...')
print('-' * 100)

cursor.execute('''
    SELECT id, kolejka, produkt, tonaz_rzeczywisty, spakowano, status
    FROM bufor
    WHERE DATE(data_planu) = %s
    ORDER BY kolejka
''', (today,))

bufor_rows = cursor.fetchall()
print(f'\nSTAN BUFORA PO DODANIU:')
if bufor_rows:
    for b in bufor_rows:
        marker = '✅' if b['status'] == 'aktywny' else '⚠️'
        print(f'  {marker} KOL={b["kolejka"]:2} | {b["produkt"]:20} | tonaz={b["tonaz_rzeczywisty"]:6.0f} kg | status={b["status"]}')
    print(f'\nRazem w buforze: {len(bufor_rows)} produktów')
else:
    print('❌ Bufor nadal pusty!')

print(f'{"="*100}\n')

cursor.close()
conn.close()
