#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Zatwierdzenie wszystkich palet w systemie z odpowiednią wagą
Ustawia status = 'przyjeta', waga_potwierdzona = waga
Tworzy wpisy w magazyn_palety, aktualizuje tonaz Magazynu
"""

from app.db import get_db_connection
from datetime import date
from collections import defaultdict

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

print(f'\n{"="*100}')
print(f'ZATWIERDZANIE PALET - {today}')
print(f'{"="*100}\n')

# ===== SPRAWDZENIE STANU PRZED =====
print('STAN PALETEK PRZED ZATWIERDZENIEM:')
print('-' * 100)

cursor.execute('''
    SELECT 
        p.id as palet_id,
        pp.produkt,
        pp.sekcja,
        p.plan_id,
        p.waga,
        p.status,
        p.waga_potwierdzona,
        p.data_dodania
    FROM palety_workowanie p
    JOIN plan_produkcji pp ON p.plan_id = pp.id
    WHERE DATE(pp.data_planu) = %s
    ORDER BY pp.sekcja, pp.produkt, p.id
''', (today,))

palety = cursor.fetchall()

if not palety:
    print('❌ Brak palet do zatwierdzenia!')
    conn.close()
    exit(1)

# Pogrupuj po produkcie
by_product = defaultdict(list)
for p in palety:
    key = f"{p['sekcja']} | {p['produkt']}"
    by_product[key].append(p)

for product_key, palet_list in sorted(by_product.items()):
    print(f'\n{product_key}:')
    for p in palet_list:
        status_str = f"status={p['status']:12}" if p['status'] else "status=            "
        waga_str = f"waga_pot={p['waga_potwierdzona']}" if p['waga_potwierdzona'] else "waga_pot=None"
        print(f'  Palet {p["palet_id"]:3} | {status_str} | waga={p["waga"]:7.0f} kg | {waga_str}')

# ===== ZATWIERDZENIE =====
print(f'\n{"="*100}')
print('ZATWIERDZANIE PALET...')
print(f'{"="*100}\n')

zatwierdzone = 0
tara = 25  # domyślna tara

for palet in palety:
    try:
        paleta_id = palet['palet_id']
        plan_id = palet['plan_id']
        waga = palet['waga']
        
        # Step 1: Aktualizuj status na 'przyjeta' oraz waga_potwierdzona
        cursor.execute('''
            UPDATE palety_workowanie 
            SET status = %s, waga_potwierdzona = %s,
                data_potwierdzenia = NOW(),
                czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW()),
                czas_rzeczywistego_potwierdzenia = SEC_TO_TIME(TIMESTAMPDIFF(SECOND, data_dodania, NOW()))
            WHERE id = %s
        ''', ('przyjeta', waga, paleta_id))
        
        # Step 2: Dodaj do magazyn_palety
        cursor.execute('''
            SELECT data_planu, produkt 
            FROM plan_produkcji 
            WHERE id = %s
        ''', (plan_id,))
        plan_info = cursor.fetchone()
        
        if plan_info:
            data_planu = plan_info['data_planu']
            produkt = plan_info['produkt']
            
            # Znajdź Magazyn plan id
            cursor.execute('''
                SELECT id FROM plan_produkcji 
                WHERE data_planu = %s AND produkt = %s AND sekcja = 'Magazyn' 
                LIMIT 1
            ''', (data_planu, produkt))
            mag_plan = cursor.fetchone()
            mag_plan_id = mag_plan['id'] if mag_plan else None
            
            # Sprawdź czy już istnieje
            cursor.execute('''
                SELECT id FROM magazyn_palety 
                WHERE paleta_workowanie_id = %s
            ''', (paleta_id,))
            exists = cursor.fetchone()
            
            if not exists:
                cursor.execute('''
                    INSERT INTO magazyn_palety 
                    (paleta_workowanie_id, plan_id, data_planu, produkt, waga_netto, waga_brutto, tara, user_login)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (paleta_id, mag_plan_id, data_planu, produkt, waga, waga + tara, tara, 'system'))
        
        zatwierdzone += 1
        
    except Exception as e:
        print(f'❌ Błąd przy zatwierdzaniu palety {palet["palet_id"]}: {e}')
        try:
            conn.rollback()
        except:
            pass

conn.commit()

# ===== SPRAWDZENIE STANU PO =====
print('STAN PALETEK PO ZATWIERDZENIU:')
print('-' * 100)

cursor.execute('''
    SELECT 
        p.id as palet_id,
        pp.produkt,
        pp.sekcja,
        p.waga,
        p.status,
        p.waga_potwierdzona
    FROM palety_workowanie p
    JOIN plan_produkcji pp ON p.plan_id = pp.id
    WHERE DATE(pp.data_planu) = %s
    ORDER BY pp.sekcja, pp.produkt, p.id
''', (today,))

palety_after = cursor.fetchall()

# Pogrupuj po produkcie
by_product_after = defaultdict(list)
for p in palety_after:
    key = f"{p['sekcja']} | {p['produkt']}"
    by_product_after[key].append(p)

for product_key, palet_list in sorted(by_product_after.items()):
    print(f'\n{product_key}:')
    for p in palet_list:
        status_str = f"status={p['status']:12}" if p['status'] else "status=            "
        waga_str = f"waga_pot={p['waga_potwierdzona']}" if p['waga_potwierdzona'] else "waga_pot=None"
        marker = '✅' if p['status'] == 'przyjeta' else '⚠️'
        print(f'  Palet {p["palet_id"]:3} | {status_str} | waga={p["waga"]:7.0f} kg | {marker} {waga_str}')

# ===== SPRAWDZENIE MAGAZYN =====
print(f'\n{"="*100}')
print('SPRAWDZENIE MAGAZYN:')
print('-' * 100)

cursor.execute('''
    SELECT 
        mp.id,
        mp.paleta_workowanie_id,
        mp.produkt,
        mp.waga_netto,
        mp.waga_brutto,
        mp.user_login
    FROM magazyn_palety mp
    WHERE DATE(mp.data_planu) = %s
    ORDER BY mp.produkt, mp.id
''', (today,))

mag_palety = cursor.fetchall()

if mag_palety:
    print(f'\nDodane do Magazynu:')
    mag_by_product = defaultdict(list)
    for mp in mag_palety:
        mag_by_product[mp['produkt']].append(mp)
    
    for prod, palet_list in sorted(mag_by_product.items()):
        print(f'  {prod}: {len(palet_list)} palet')
        for mp in palet_list:
            print(f'    - Palet workowania ID={mp["paleta_workowanie_id"]:3} | netto={mp["waga_netto"]:5.0f} kg | brutto={mp["waga_brutto"]:5.0f} kg | user={mp["user_login"]}')
else:
    print('  ❌ Brak palet w Magazynie')

# ===== PODSUMOWANIE =====
print(f'\n{"="*100}')
print(f'✅ ZATWIERDZANIE PALET ZAKOŃCZONE')
print(f'{"="*100}')

# Statystyka końcowa
cursor.execute('''
    SELECT 
        pp.produkt,
        COUNT(p.id) as ile_palet,
        SUM(p.waga) as suma_wagi,
        SUM(CASE WHEN p.status='przyjeta' THEN 1 ELSE 0 END) as zaakceptowane_szt
    FROM palety_workowanie p
    JOIN plan_produkcji pp ON p.plan_id = pp.id
    WHERE DATE(pp.data_planu) = %s
    GROUP BY pp.produkt
    ORDER BY pp.produkt
''', (today,))

stats = cursor.fetchall()

print(f'\nPODSUMOWANIE PO PRODUKTACH:')
for s in stats:
    marker = '✅' if s['zaakceptowane_szt'] == s['ile_palet'] else '⚠️'
    print(f'  {marker} {s["produkt"]:20} | Palet: {s["ile_palet"]:2} szt | Suma wagi: {s["suma_wagi"]:8.0f} kg | Zaakceptowane: {s["zaakceptowane_szt"]:2} szt')

print(f'\nRazem zatwierdzono: {zatwierdzone} palet')
print(f'{"="*100}\n')

cursor.close()
conn.close()
