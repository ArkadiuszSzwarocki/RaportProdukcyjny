from app.db import get_db_connection
from datetime import date, datetime
import json

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# Dzisiejsza data: 2026-07-09
today = date(2026, 7, 9)

print('=' * 70)
print(f'🔍 DOSTAWY Z DNIA {today.strftime("%d.%m.%Y")}')
print('=' * 70)

# Znajdź wszystkie dostawy z dzisiejszej daty
cur.execute('''
    SELECT id, order_ref, linia, lokalizacja_z, lokalizacja_do, status, 
           created_at, items 
    FROM magazyn_dostawy 
    WHERE DATE(created_at) = %s 
    ORDER BY created_at DESC
''', (today,))

dostawy = cur.fetchall()

print(f'\n✅ Znaleziono: {len(dostawy)} dostaw/przyjęć')

for idx, d in enumerate(dostawy, 1):
    print(f'\n📦 #{idx} | ID: {d["id"][:12]}...')
    print(f'   Numer WZ: {d["order_ref"]}')
    print(f'   Linia: {d["linia"]}')
    print(f'   Skąd: {d["lokalizacja_z"] or "ZEWNĘTRZNA"}')
    print(f'   Dokąd: {d["lokalizacja_do"] or "WYDANIE"}')
    print(f'   Status: {d["status"]}')
    print(f'   Data: {d["created_at"]}')
    
    # Parsuj items
    if d.get('items'):
        try:
            items = json.loads(d['items'])
            if isinstance(items, list):
                print(f'   Palety: {len(items)} szt.')
                for i, item in enumerate(items[:3], 1):  # Pokażę max 3 pierwsze
                    nr_pal = item.get('nr_palety') or item.get('sourcePalletNo') or '???'
                    produkt = item.get('productName') or '???'
                    waga = item.get('netWeight') or item.get('unitsPerPallet') or 0
                    print(f'      {i}. {nr_pal}: {produkt} ({waga} kg)')
                if len(items) > 3:
                    print(f'      ... i {len(items) - 3} więcej')
        except Exception as e:
            print(f'   ⚠️  Błąd parsowania items: {e}')

conn.close()

print('\n' + '=' * 70)
print('DOSTĘPNE AKCJE:')
print('=' * 70)
print('1. Wydrukuj etykiety dla konkretnej dostawy')
print('2. Wydrukuj etykiety dla wszystkich dostaw z dzisiaj')
print('3. Wyświetl szczegóły konkretnej dostawy')
