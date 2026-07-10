from app.db import get_db_connection
from datetime import date
import json
import requests
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Konfiguracja
TODAY = date(2026, 7, 9)
PRINTER_SERVER = "http://127.0.0.1:3001/drukuj-zpl"

print('=' * 70)
print(f'📄 GENEROWANIE ETYKIET Z DOSTAW - {TODAY.strftime("%d.%m.%Y")}')
print('=' * 70)

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

# 1. Pobierz dostępne drukarki
cur.execute("SELECT id, nazwa, ip, aktywna FROM drukarki ORDER BY id")
drukarki = cur.fetchall()

print('\n🖨️  Dostępne drukarki:')
for d in drukarki:
    status = '✅ AKTYWNA' if d['aktywna'] else '❌ NIEAKTYWNA'
    print(f'   {d["id"]}. {d["nazwa"]} ({d["ip"]}) - {status}')

active_printers = [d for d in drukarki if d['aktywna']]
if not active_printers:
    print('\n❌ Brak aktywnych drukarek!')
    conn.close()
    exit(1)

# Wybierz pierwszą aktywną drukarkę
selected_printer = active_printers[0]
print(f'\n✅ Wybrana drukarka: {selected_printer["nazwa"]} ({selected_printer["ip"]})')

# 2. Pobierz dostawy COMPLETED z dzisiaj
cur.execute('''
    SELECT id, order_ref, linia, lokalizacja_z, lokalizacja_do, 
           created_at, items 
    FROM magazyn_dostawy 
    WHERE DATE(created_at) = %s AND status = 'COMPLETED'
    ORDER BY created_at DESC
''', (TODAY,))

dostawy = cur.fetchall()

print(f'\n📦 Znaleziono {len(dostawy)} dostaw COMPLETED z {TODAY.strftime("%d.%m.%Y")}')

if not dostawy:
    print('\n❌ Brak dostaw do wydruku!')
    conn.close()
    exit(0)

# 3. Generuj etykiety
total_labels = 0
successful_prints = 0
failed_prints = 0

for idx, dostawa in enumerate(dostawy, 1):
    print(f'\n--- Dostawa #{idx}: {dostawa["order_ref"]} ---')
    
    if not dostawa.get('items'):
        print('   ⚠️  Brak pozycji w dostawie')
        continue
    
    try:
        items = json.loads(dostawa['items'])
    except Exception as e:
        print(f'   ❌ Błąd parsowania items: {e}')
        continue
    
    if not isinstance(items, list):
        print('   ⚠️  Items nie jest listą')
        continue
    
    print(f'   Palety: {len(items)} szt.')
    
    for item_idx, item in enumerate(items, 1):
        nr_palety = item.get('nr_palety') or item.get('sourcePalletNo') or f'PAL-{item_idx}'
        product_name = item.get('productName') or 'Brak nazwy'
        nr_partii = item.get('nr_partii') or '---'
        data_produkcji = item.get('data_produkcji') or '---'
        data_przydatnosci = item.get('data_przydatnosci') or '---'
        qty = item.get('netWeight') or item.get('unitsPerPallet') or 0
        p_type = 'opakowanie' if item.get('packageForm') == 'packaging' else 'surowiec'
        
        typ_label = 'OPAKOWANIE' if p_type == 'opakowanie' else 'SUROWIEC'
        
        # Generuj ZPL
        zpl_code = f"""^XA
^CI28
^PW812^LL1214
^FO20,20^GB772,1174,4^FS
^FO40,60^A0N,50,50^FD{typ_label} - {dostawa['linia']}^FS
^FO40,150^A0N,65,65^FB720,3,0,C^FD{product_name[:40]}^FS
^FO250,340^BQN,2,10^FDQA,{nr_palety}^FS
^FO40,650^A0N,55,55^FB720,1,0,C^FD{nr_palety}^FS
^FO40,750^A0N,50,50^FDPARTIA: {nr_partii}^FS
^FO40,850^A0N,50,50^FDPRODUKCJA: {data_produkcji}^FS
^FO40,950^A0N,50,50^FDPRZYDATNOSC: {data_przydatnosci}^FS
^FO40,1100^A0N,70,70^FDWAGA: {qty} kg^FS
^XZ"""
        
        print(f'      {item_idx}. {nr_palety}: {product_name[:30]}... ({qty} kg)')
        
        # Wyślij do drukarki (2 egzemplarze)
        payload = {
            "drukarka": selected_printer["nazwa"],
            "ip": selected_printer["ip"],
            "typ": p_type,
            "dane": zpl_code
        }
        
        for copy in range(1, 3):  # 2 egzemplarze
            try:
                response = requests.post(
                    PRINTER_SERVER,
                    json=payload,
                    verify=False,
                    timeout=5
                )
                if response.status_code == 200:
                    successful_prints += 1
                    if copy == 1:
                        print(f'         ✅ Wysłano etykietę (egz. {copy}/2)')
                else:
                    failed_prints += 1
                    print(f'         ❌ Błąd drukarki (egz. {copy}/2): {response.status_code}')
            except Exception as e:
                failed_prints += 1
                print(f'         ❌ Błąd wysyłania (egz. {copy}/2): {e}')
            
            # Opóźnienie między wysyłkami aby zachować kolejność
            time.sleep(0.3)
        
        total_labels += 1

conn.close()

print('\n' + '=' * 70)
print('PODSUMOWANIE')
print('=' * 70)
print(f'✅ Przetworzono: {total_labels} etykiet (x2 egzemplarze)')
print(f'✅ Wysłano pomyślnie: {successful_prints} wydruków')
print(f'❌ Błędy: {failed_prints} wydruków')
print(f'🖨️  Drukarka: {selected_printer["nazwa"]} ({selected_printer["ip"]})')
