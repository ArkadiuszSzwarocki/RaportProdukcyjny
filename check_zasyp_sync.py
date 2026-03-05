#!/usr/bin/env python
"""
Sprawdź czy tonaz_rzeczywisty w DB = suma szarż dla Zasypu dzisiaj
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

print(f'\n{"="*100}')
print(f'SPRAWDZENIE: tonaz_rzeczywisty (DB) vs SUM(szarże) dla Zasypu ({today})')
print(f'{"="*100}\n')

# Pobierz wszystkie plany Zasypu dzisiaj
cursor.execute('''
    SELECT p.id, p.produkt, p.tonaz, p.tonaz_rzeczywisty, p.status
    FROM plan_produkcji p
    WHERE sekcja='Zasyp' AND DATE(data_planu)=%s
    ORDER BY p.produkt
''', (today,))
plans = cursor.fetchall()

for p in plans:
    plan_id = p['id']
    produkt = p['produkt']
    tonaz_db = p['tonaz_rzeczywisty'] or 0
    
    # Oblicz sumę szarż dla tego planu
    cursor.execute('''
        SELECT COALESCE(SUM(waga), 0) as szarze_sum
        FROM szarze
        WHERE plan_id=%s
    ''', (plan_id,))
    
    szarze_row = cursor.fetchone()
    szarze_sum = szarze_row['szarze_sum'] if szarze_row else 0
    
    # Porównaj
    if abs(tonaz_db - szarze_sum) < 0.01:
        status = '✓'
    else:
        status = '✗'
    
    print(f'{status} {produkt:20} | DB={tonaz_db:8.0f} | SUMA_SZARŻ={szarze_sum:8.0f} | Plan={p["tonaz"]:8.0f} | Status={p["status"]}')

conn.close()
print(f'\n{"="*100}\n')
