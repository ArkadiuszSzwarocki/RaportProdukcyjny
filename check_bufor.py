#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdzenie bufora - gdzie jest MOM INSTANT?
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'SPRAWDZENIE BUFORA - {today}')
print(f'{"="*100}\n')

# Co jest w buforze
print('CO JEST W BUFORZE:')
print('-' * 100)
cursor.execute('''
    SELECT 
        id, zasyp_id, produkt, tonaz_rzeczywisty, spakowano, kolejka, status, created_at
    FROM bufor
    WHERE DATE(data_planu) = %s
    ORDER BY kolejka
''', (today,))

bufor_rows = cursor.fetchall()

if not bufor_rows:
    print('❌ BUFOR PUSTY!')
else:
    for b in bufor_rows:
        print(f'  KOL={b["kolejka"]:2} | {b["produkt"]:20} | status={b["status"]:12} | tonaz={b["tonaz_rzeczywisty"]:6.0f} kg | spakowano={b["spakowano"]:6.0f} kg')

# Stan produktów
print(f'\n{"="*100}')
print('STATUS PRODUKTÓW:')
print('-' * 100)

produkty = ['HOLENDER', 'MILK BAND BIAŁE', 'MOM INSTANT']

for prod in produkty:
    print(f'\n{prod}:')
    
    # Zasyp
    cursor.execute('''
        SELECT id, status, real_start, real_stop, tonaz_rzeczywisty
        FROM plan_produkcji
        WHERE sekcja = 'Zasyp' AND produkt = %s AND DATE(data_planu) = %s
    ''', (prod, today))
    zasyp = cursor.fetchone()
    
    if zasyp:
        print(f'  Zasyp  | id={zasyp["id"]} | status={zasyp["status"]:12} | tonaz={zasyp["tonaz_rzeczywisty"]:.0f} kg | stop={zasyp["real_stop"]}')
    else:
        print(f'  Zasyp  | ❌ brak')
    
    # Workowanie
    cursor.execute('''
        SELECT id, status, real_start, real_stop, tonaz_rzeczywisty
        FROM plan_produkcji
        WHERE sekcja = 'Workowanie' AND produkt = %s AND DATE(data_planu) = %s
    ''', (prod, today))
    work = cursor.fetchone()
    
    if work:
        print(f'  Work   | id={work["id"]} | status={work["status"]:12} | tonaz={work["tonaz_rzeczywisty"]:.0f} kg | start={work["real_start"]}')
    else:
        print(f'  Work   | ❌ brak')
    
    # Bufor
    cursor.execute('''
        SELECT id, kolejka, status, tonaz_rzeczywisty, spakowano
        FROM bufor
        WHERE produkt = %s AND DATE(data_planu) = %s
    ''', (prod, today))
    buf = cursor.fetchone()
    
    if buf:
        print(f'  Bufor  | id={buf["id"]} | kol={buf["kolejka"]} | status={buf["status"]:12} | tonaz={buf["tonaz_rzeczywisty"]:.0f} kg')
    else:
        print(f'  Bufor  | ❌ brak w buforze!')

# Sprawdzenie logiki
print(f'\n{"="*100}')
print('ANALIZA:')
print('-' * 100)

cursor.execute('''
    SELECT COUNT(*) as cnt FROM bufor 
    WHERE DATE(data_planu) = %s AND status = 'aktywny'
''', (today,))
active = cursor.fetchone()['cnt']

cursor.execute('''
    SELECT COUNT(*) as cnt FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
''', (today,))
work_plans = cursor.fetchone()['cnt']

print(f'Planów Workowanie: {work_plans}')
print(f'Aktywnych w buforze: {active}')

if active < work_plans:
    print(f'\n💡 PROBLEM: Brakuje {work_plans - active} produktów w buforze!')
    print(f'   Sprawdzam które produkty Workowania nie mają wpisu w buforze...\n')
    
    cursor.execute('''
        SELECT pp.id, pp.produkt
        FROM plan_produkcji pp
        WHERE pp.sekcja = 'Workowanie' AND DATE(pp.data_planu) = %s
        AND pp.produkt NOT IN (
            SELECT produkt FROM bufor WHERE DATE(data_planu) = %s
        )
    ''', (today, today))
    
    missing = cursor.fetchall()
    for m in missing:
        print(f'   ⚠️  {m["produkt"]:20} (Workowanie ID={m["id"]}) - BRAKUJE w buforze!')

print(f'{"="*100}\n')

cursor.close()
conn.close()
