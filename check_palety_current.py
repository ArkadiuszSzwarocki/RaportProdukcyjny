#!/usr/bin/env python
"""
Sprawdź obecny stan paletek dla dzisiejszych zleceń
"""
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

today = date.today()

print(f'\n{"="*100}')
print(f'STAN PALETEK DLA ZLECEŃ DZISIAJ ({today})')
print(f'{"="*100}\n')

# Pobierz wszystkie plany Zasypu dzisiaj
cursor.execute('''
    SELECT p.id, p.produkt, p.tonaz_rzeczywisty, p.sekcja
    FROM plan_produkcji p
    WHERE DATE(data_planu)=%s AND is_deleted=0
    ORDER BY p.sekcja, p.produkt
''', (today,))

plans = cursor.fetchall()

for p in plans:
    plan_id = p['id']
    produkt = p['produkt']
    tonaz = p['tonaz_rzeczywisty'] or 0
    sekcja = p['sekcja']
    
    # Pobierz palety dla tego planu
    cursor.execute('''
        SELECT COUNT(*) as cnt, COALESCE(SUM(waga), 0) as sumwagi
        FROM palety_workowanie
        WHERE plan_id=%s
    ''', (plan_id,))
    
    pal_row = cursor.fetchone()
    pal_count = pal_row['cnt'] if pal_row else 0
    pal_sum = pal_row['sumwagi'] if pal_row else 0
    
    print(f'{sekcja:12} | {produkt:20} | Plan={tonaz:8.0f} kg | Palety: {pal_count:2} szt (= {pal_sum:8.0f} kg)')

conn.close()
print(f'\n{"="*100}\n')
