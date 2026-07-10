from app.services.scanner_service import ScannerService

print('=' * 70)
print('FINALNY TEST - CO DZIAŁA, A CO NIE')
print('=' * 70)

tests = [
    ('AGR000001782288263514', 'AGRO', 'Kod AGR na skanerze AGRO'),
    ('AGR000001782288263514', 'PSD', 'Kod AGR na skanerze PSD (błędna linia)'),
    ('PSD020320262455411041', 'PSD', 'Kod PSD na skanerze PSD'),
    ('PSD020320262455411041', 'AGRO', 'Kod PSD na skanerze AGRO (błędna linia)'),
]

for code, linia, opis in tests:
    print(f'\n📋 {opis}')
    print(f'   Kod: {code}')
    print(f'   Linia: {linia}')
    
    result = ScannerService.lookup_by_location(code, linia)
    
    if result:
        print(f'   ✅ ZNALEZIONO')
        print(f'      Nazwa: {result["nazwa"]}')
        print(f'      ID: {result["id"]}')
        print(f'      Typ: {result["inventory_type"]}')
        print(f'      Lokalizacja: {result["lokalizacja"]}')
    else:
        print(f'   ❌ NIE ZNALEZIONO')

print('\n' + '=' * 70)
print('PODSUMOWANIE')
print('=' * 70)
print('''
Z bazy danych wiemy że:
- PSD020320262455411041 → NIE ISTNIEJE (w żadnej tabeli)
- AGR000001782288263514 → ISTNIEJE w magazyn_palety_agro

Oczekiwane wyniki:
✅ AGR na AGRO → powinien znaleźć
❌ AGR na PSD  → nie powinien znaleźć (inna linia)
❌ PSD na PSD  → nie powinien znaleźć (nie ma w bazie)
❌ PSD na AGRO → nie powinien znaleźć (inna linia + nie ma w bazie)
''')
