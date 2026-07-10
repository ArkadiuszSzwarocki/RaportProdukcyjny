from app.services.scanner_service import ScannerService

code1 = 'PSD020320262455411041'
code2 = 'AGR000001782288263514'

print('=' * 70)
print('TEST KODÓW SSCC')
print('=' * 70)

print(f'\n1️⃣ Kod: {code1}')
print(f'   Długość: {len(code1)}')
result1 = ScannerService.lookup_by_location(code1, 'PSD')
if result1:
    print(f'   ✅ ZNALEZIONO: {result1["nazwa"]}')
    print(f'   📍 Lokalizacja: {result1["lokalizacja"]}')
    print(f'   📦 Typ: {result1["inventory_type"]}')
else:
    print('   ❌ NIE ZNALEZIONO')

print(f'\n2️⃣ Kod: {code2}')
print(f'   Długość: {len(code2)}')
result2 = ScannerService.lookup_by_location(code2, 'AGRO')
if result2:
    print(f'   ✅ ZNALEZIONO: {result2["nazwa"]}')
    print(f'   📍 Lokalizacja: {result2["lokalizacja"]}')
    print(f'   📦 Typ: {result2["inventory_type"]}')
else:
    print('   ❌ NIE ZNALEZIONO')

# Test normalizacji
print('\n' + '=' * 70)
print('TEST NORMALIZACJI')
print('=' * 70)
normalized1 = ScannerService._normalize_scanned_code(code1)
normalized2 = ScannerService._normalize_scanned_code(code2)
print(f'\nPSD normalized: {normalized1}')
print(f'AGR normalized: {normalized2}')

# Test czy to SSCC
is_sscc1 = ScannerService._is_sscc_code(normalized1)
is_sscc2 = ScannerService._is_sscc_code(normalized2)
print(f'\nPSD is_sscc: {is_sscc1}')
print(f'AGR is_sscc: {is_sscc2}')

# Test prefixów
prefix1, id1 = ScannerService._extract_prefixed_id(normalized1)
prefix2, id2 = ScannerService._extract_prefixed_id(normalized2)
print(f'\nPSD prefix: {prefix1}, id: {id1}')
print(f'AGR prefix: {prefix2}, id: {id2}')
