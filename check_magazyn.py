#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdzenie magazyn_palety - czy nie ma duplikatów/nadliczbowych palet
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'SPRAWDZENIE MAGAZYN_PALETY - {today}')
print(f'{"="*100}\n')

# Sprawdź ile palet w magazynie
cursor.execute('''
    SELECT 
        mp.produkt,
        COUNT(mp.id) as ile_palet,
        SUM(mp.waga_netto) as suma_netto,
        SUM(mp.waga_brutto) as suma_brutto
    FROM magazyn_palety mp
    WHERE DATE(mp.data_planu) = %s
    GROUP BY mp.produkt
    ORDER BY mp.produkt
''', (today,))

stats = cursor.fetchall()

print('PODSUMOWANIE MAGAZYN PO PRODUKTACH:')
total_palet = 0
for s in stats:
    print(f'  {s["produkt"]:20} | Palet: {s["ile_palet"]:2} szt | Netto: {s["suma_netto"]:.0f} kg | Brutto: {s["suma_brutto"]:.0f} kg')
    total_palet += s['ile_palet']

print(f'\nRazem w magazynie: {total_palet} palet')

# Sprawdź ile powinno być (Workowanie)
print(f'\n{"="*100}')
print('CO POWINNO BYĆ (tylko Workowanie):')
cursor.execute('''
    SELECT 
        pp.produkt,
        COUNT(pw.id) as ile_palet,
        SUM(pw.waga) as suma_wagi
    FROM palety_workowanie pw
    JOIN plan_produkcji pp ON pw.plan_id = pp.id
    WHERE pp.sekcja = 'Workowanie' AND DATE(pp.data_planu) = %s
    GROUP BY pp.produkt
    ORDER BY pp.produkt
''', (today,))

workowanie = cursor.fetchall()
total_work = 0
for w in workowanie:
    print(f'  {w["produkt"]:20} | Palet: {w["ile_palet"]:2} szt | Waga: {w["suma_wagi"]:.0f} kg')
    total_work += w['ile_palet']

print(f'\nRazem Workowanie (powinno): {total_work} palet')

# Sprawdzenie szczegółów - skąd pochodzą palety
print(f'\n{"="*100}')
print('ANALIZA ŹRÓDŁA PALET:')
print('-' * 100)

cursor.execute('''
    SELECT 
        mp.id,
        mp.paleta_workowanie_id,
        mp.produkt,
        mp.plan_id,
        pp.sekcja as plan_sekcja
    FROM magazyn_palety mp
    LEFT JOIN plan_produkcji pp ON mp.plan_id = pp.id
    WHERE DATE(mp.data_planu) = %s
    ORDER BY mp.produkt, mp.paleta_workowanie_id
''', (today,))

all_mag = cursor.fetchall()

# Pogrupuj po źródle
from collections import defaultdict
by_source = defaultdict(lambda: defaultdict(list))

for m in all_mag:
    sekcja = m['plan_sekcja'] if m['plan_sekcja'] else 'UNKNOWN'
    produkt = m['produkt']
    by_source[sekcja][produkt].append(m)

for sekcja in sorted(by_source.keys()):
    print(f'\nZ sekcji {sekcja}:')
    count = 0
    for produkt, palet_list in sorted(by_source[sekcja].items()):
        print(f'  {produkt}: {len(palet_list)} palet')
        count += len(palet_list)
    print(f'  Razem z {sekcja}: {count} palet')

# Porównanie
print(f'\n{"="*100}')
print('PODSUMOWANIE:')
print('-' * 100)
if total_palet > total_work:
    print(f'⚠️  PROBLEM: W magazynie {total_palet} palet, a powinno {total_work}!')
    print(f'Nadliczbowych: {total_palet - total_work} palet')
    print(f'\n💡 Może być że dodane zostały palety zarówno z Zasyp jak i z Workowania')
    print(f'   Powinno być TYLKO palety z Workowania!')
elif total_palet == total_work:
    print(f'✅ OK: Ilości się zgadzają ({total_work} palet)')
else:
    print(f'❌ ERROR: W magazynie {total_palet} palet, a powinno {total_work}!')
    print(f'Brakuje: {total_work - total_palet} palet')

print(f'{"="*100}\n')

conn.close()
