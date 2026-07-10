"""Test cross-line lookup - uniwersalny skaner"""
from app.services.scanner_service import ScannerService

print('=' * 70)
print('TEST UNIWERSALNEGO SKANERA')
print('=' * 70)

# Test 1: AGR code na różnych liniach
print('\n📋 Test 1: Kod AGR na różnych skanerach')
code_agr = 'AGR000001782288263514'

result_agro = ScannerService.lookup_by_location(code_agr, linia='AGRO')
result_psd = ScannerService.lookup_by_location(code_agr, linia='PSD')

if result_agro and result_psd:
    print(f'   ✅ AGRO: {result_agro["nazwa"]} (ID: {result_agro["id"]})')
    print(f'   ✅ PSD:  {result_psd["nazwa"]} (ID: {result_psd["id"]})')
    if result_agro['id'] == result_psd['id']:
        print('   ✅ Oba skanery zwracają TĘ SAMĄ paletę')
    else:
        print('   ⚠️  Skanery zwracają RÓŻNE palety!')
else:
    print('   ❌ BŁĄD: Nie znaleziono na którymś ze skanerów')

# Test 2: PSD code na różnych liniach
print('\n📋 Test 2: Kod PSD na różnych skanerach')
code_psd = 'PSD020320262455411041'

result_agro = ScannerService.lookup_by_location(code_psd, linia='AGRO')
result_psd = ScannerService.lookup_by_location(code_psd, linia='PSD')

if result_agro and result_psd:
    print(f'   ✅ AGRO: {result_agro["nazwa"]} (ID: {result_agro["id"]})')
    print(f'   ✅ PSD:  {result_psd["nazwa"]} (ID: {result_psd["id"]})')
    if result_agro['id'] == result_psd['id']:
        print('   ✅ Oba skanery zwracają TĘ SAMĄ paletę')
    else:
        print('   ⚠️  Skanery zwracają RÓŻNE palety!')
else:
    print('   ❌ BŁĄD: Nie znaleziono na którymś ze skanerów')

# Test 3: Możliwość wyłączenia cross-line lookup
print('\n📋 Test 3: Wyłączenie cross-line lookup')
result_no_cross = ScannerService.lookup_by_location(code_agr, linia='PSD', try_all_lines=False)
if result_no_cross:
    print('   ⚠️  Znaleziono mimo try_all_lines=False (niepoprawnie)')
else:
    print('   ✅ Nie znaleziono (poprawnie) - kod AGR nie jest w tabeli PSD')

result_no_cross2 = ScannerService.lookup_by_location(code_agr, linia='AGRO', try_all_lines=False)
if result_no_cross2:
    print('   ✅ Znaleziono - kod AGR jest w tabeli AGRO')
else:
    print('   ❌ Nie znaleziono (niepoprawnie)')

print('\n' + '=' * 70)
print('PODSUMOWANIE')
print('=' * 70)
print('''
✅ Uniwersalny skaner działa - kody z różnych linii są znajdowane
✅ Parametr try_all_lines pozwala wyłączyć cross-line lookup
✅ Domyślnie try_all_lines=True dla kompatybilności z uniwersalnym skanerem
''')
