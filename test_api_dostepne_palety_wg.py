import requests
import json

# Test endpointu /api/dostepne-palety z kodem wyrobu gotowego
base_url = "http://127.0.0.1:8082"

test_cases = [
    {
        'desc': 'Kod SSCC wyrobu gotowego AGRO',
        'params': {'linia': 'AGRO', 'prefix': 'AGR220420266849278003'}
    },
    {
        'desc': 'Kod SSCC wyrobu gotowego PSD (jeśli istnieje)',
        'params': {'linia': 'PSD', 'prefix': 'PSD020320262455411041'}
    },
    {
        'desc': 'Wyszukiwanie uniwersalne (wszystkie linie) - kod AGRO',
        'params': {'linia': 'PSD', 'prefix': 'AGR220420266849278003'}
    },
    {
        'desc': 'Wyszukiwanie po lokalizacji MGW01',
        'params': {'linia': 'AGRO', 'prefix': 'MGW01'}
    },
]

print('=' * 80)
print('TEST ENDPOINTU /api/dostepne-palety - WYROBY GOTOWE')
print('=' * 80)

for tc in test_cases:
    print(f'\n📋 Test: {tc["desc"]}')
    print(f'   Parametry: {tc["params"]}')
    
    try:
        response = requests.get(f'{base_url}/magazyn-dostawy/api/dostepne-palety', params=tc['params'])
        
        if response.status_code != 200:
            print(f'   ❌ Błąd HTTP {response.status_code}')
            continue
        
        data = response.json()
        
        if not data.get('success'):
            print(f'   ❌ API zwróciło success=false')
            continue
        
        pallets = data.get('pallets', [])
        print(f'   ✅ Znaleziono: {len(pallets)} palet')
        
        # Zlicz typy
        types = {}
        for p in pallets:
            t = p.get('type', 'unknown')
            types[t] = types.get(t, 0) + 1
        
        print(f'   📊 Typy: {dict(types)}')
        
        # Pokaż pierwsze 3 wyroby gotowe
        wg = [p for p in pallets if p.get('type') == 'wyrob_gotowy']
        if wg:
            print(f'   🎯 Wyroby gotowe ({len(wg)}):')
            for p in wg[:3]:
                print(f'      - {p.get("nr_palety")}: {p.get("nazwa")} ({p.get("stan_magazynowy")} kg) @ {p.get("lokalizacja")}')
        
    except Exception as e:
        print(f'   ❌ Błąd: {e}')

print('\n' + '=' * 80)
print('✅ Test zakończony')
