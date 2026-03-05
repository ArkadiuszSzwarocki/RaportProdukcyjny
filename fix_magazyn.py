#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Naprawa magazyn_palety - usunięcie duplikatów i dodanie prawidłowych palet
"""

from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
today = date.today()

print(f'\n{"="*100}')
print(f'NAPRAWA MAGAZYN_PALETY - {today}')
print(f'{"="*100}\n')

# ===== USUNIĘCIE ZŁYCH WPISÓW =====
print('KROK 1: Usunięcie złych wpisów z magazyn_palety...')
cursor.execute('''
    SELECT COUNT(*) as cnt FROM magazyn_palety 
    WHERE DATE(data_planu) = %s
''', (today,))
przed = cursor.fetchone()['cnt']
print(f'  Przed: {przed} palet')

cursor.execute('''
    DELETE FROM magazyn_palety 
    WHERE DATE(data_planu) = %s
''', (today,))
conn.commit()

cursor.execute('''
    SELECT COUNT(*) as cnt FROM magazyn_palety 
    WHERE DATE(data_planu) = %s
''', (today,))
po = cursor.fetchone()['cnt']
print(f'  Po: {po} palet')
print(f'  ✅ Usunięto: {przed - po} palet\n')

# ===== DODANIE PRAWIDŁOWYCH PALET =====
print('KROK 2: Dodanie palet z Workowania...')

# Mapa Zasyp <-> Workowanie
mapowanie = {
    1368: 1369,  # HOLENDER
    1366: 1367,  # MILK BAND BIAŁE
    1364: 1365   # MOM INSTANT
}

tara = 25

# Pobierz palet z Workowania
cursor.execute('''
    SELECT 
        pw.id as palet_id,
        pw.plan_id,
        pw.waga,
        pp.produkt,
        pp.data_planu
    FROM palety_workowanie pw
    JOIN plan_produkcji pp ON pw.plan_id = pp.id
    WHERE pp.sekcja = 'Workowanie' AND DATE(pp.data_planu) = %s
    ORDER BY pp.produkt, pw.id
''', (today,))

palety = cursor.fetchall()

if not palety:
    print('❌ Brak palet Workowania!')
    conn.close()
    exit(1)

dodane = 0
for palet in palety:
    paleta_id = palet['palet_id']
    plan_id = palet['plan_id']
    waga = palet['waga']
    produkt = palet['produkt']
    data_planu = palet['data_planu']
    
    cursor.execute('''
        INSERT INTO magazyn_palety 
        (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ''', (paleta_id, plan_id, data_planu, produkt, waga, waga + tara, tara, 'system'))
    
    dodane += 1

conn.commit()

print(f'  ✅ Dodano: {dodane} palet\n')

# ===== WERYFIKACJA =====
print('KROK 3: Weryfikacja...')

cursor.execute('''
    SELECT 
        mp.produkt,
        COUNT(mp.id) as ile_palet,
        SUM(mp.waga_netto) as suma_netto
    FROM magazyn_palety mp
    WHERE DATE(mp.data_planu) = %s
    GROUP BY mp.produkt
    ORDER BY mp.produkt
''', (today,))

stats = cursor.fetchall()

print('STAN PO NAPRAWIE:')
total = 0
for s in stats:
    print(f'  {s["produkt"]:20} | Palet: {s["ile_palet"]:2} szt | Netto: {s["suma_netto"]:.0f} kg')
    total += s['ile_palet']

# Porównaj z Workowanie
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
    total_work += w['ile_palet']

print(f'\nRazem w magazynie: {total} palet')
print(f'Powinno być (Workowanie): {total_work} palet')

if total == total_work:
    print(f'\n✅ SUKCES! Magazyn naprawiony prawidłowo!')
else:
    print(f'\n⚠️  UWAGA! Liczby się nie zgadzają!')

print(f'{"="*100}\n')

cursor.close()
conn.close()
