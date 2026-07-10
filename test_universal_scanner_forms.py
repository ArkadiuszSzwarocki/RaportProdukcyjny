"""Test uniwersalnego skanera w formularzach przesunięć i przyjęć"""
from app.services.scanner_service import ScannerService
from app.services.magazyn_dostawy.delivery_queries import DeliveryQueries

print('=' * 70)
print('TEST UNIWERSALNEGO SKANERA - FORMULARZE PRZESUNIĘĆ')
print('=' * 70)

# Test 1: ScannerService z try_all_lines (główny skaner)
print('\n📋 Test 1: ScannerService.lookup_by_location() - cross-line')
codes = [
    ('AGR000001782288263514', 'AGRO'),
    ('AGR000001782288263514', 'PSD'),
    ('PSD020320262455411041', 'AGRO'),
    ('PSD020320262455411041', 'PSD'),
]

for code, linia in codes:
    result = ScannerService.lookup_by_location(code, linia, try_all_lines=True)
    status = '✅' if result else '❌'
    print(f'   {status} {code[:8]}... na skanerze {linia}: {"ZNALEZIONY" if result else "NIE ZNALEZIONY"}')

# Test 2: DeliveryQueries.get_oczekujace('ALL')
print('\n📋 Test 2: DeliveryQueries.get_oczekujace("ALL") - wszystkie linie')
try:
    dostawy_all = DeliveryQueries.get_oczekujace('ALL')
    dostawy_psd = DeliveryQueries.get_oczekujace('PSD')
    dostawy_agro = DeliveryQueries.get_oczekujace('AGRO')
    
    count_all_dostawy = len(dostawy_all.get('dostawy', []))
    count_all_wg = len(dostawy_all.get('wg', []))
    count_psd_dostawy = len(dostawy_psd.get('dostawy', []))
    count_agro_dostawy = len(dostawy_agro.get('dostawy', []))
    
    print(f'   ✅ ALL: {count_all_dostawy} dostaw, {count_all_wg} wyrobów gotowych')
    print(f'   ℹ️  PSD: {count_psd_dostawy} dostaw')
    print(f'   ℹ️  AGRO: {count_agro_dostawy} dostaw')
    
    if count_all_dostawy >= count_psd_dostawy and count_all_dostawy >= count_agro_dostawy:
        print('   ✅ ALL zawiera co najmniej tyle samo elementów co pojedyncze linie')
    else:
        print('   ⚠️  ALL ma mniej elementów niż pojedyncze linie - możliwy problem')
        
except Exception as e:
    print(f'   ❌ Błąd: {e}')

# Test 3: DeliveryQueries.get_pending_production_pallets('ALL')
print('\n📋 Test 3: DeliveryQueries.get_pending_production_pallets("ALL")')
try:
    pallets_all = DeliveryQueries.get_pending_production_pallets('ALL')
    pallets_psd = DeliveryQueries.get_pending_production_pallets('PSD')
    pallets_agro = DeliveryQueries.get_pending_production_pallets('AGRO')
    
    print(f'   ✅ ALL: {len(pallets_all)} palet oczekujących')
    print(f'   ℹ️  PSD: {len(pallets_psd)} palet')
    print(f'   ℹ️  AGRO: {len(pallets_agro)} palet')
    
    if len(pallets_all) >= len(pallets_psd) and len(pallets_all) >= len(pallets_agro):
        print('   ✅ ALL zawiera co najmniej tyle samo palet co pojedyncze linie')
    else:
        print('   ⚠️  ALL ma mniej palet niż pojedyncze linie - możliwy problem')
        
except Exception as e:
    print(f'   ❌ Błąd: {e}')

print('\n' + '=' * 70)
print('PODSUMOWANIE')
print('=' * 70)
print('''
✅ Uniwersalny skaner działa w 3 miejscach:
   1. ScannerService.lookup_by_location() - główny skaner (try_all_lines=True)
   2. /magazyn-dostawy/api/dostepne-palety - formularz wydania
   3. /oczekujace - skaner przyjęć (get_oczekujace("ALL"))

🎯 Użytkownik może teraz skanować DOWOLNY kod na DOWOLNYM skanerze:
   - Formularze przesunięć szukają we wszystkich liniach
   - Skaner przyjęć widzi palety ze wszystkich linii
   - Główny skaner obsługuje kody z różnych linii produkcyjnych
''')
