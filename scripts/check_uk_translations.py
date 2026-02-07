import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

pl_keys = set(data.get('pl', {}).keys())
uk_keys = set(data.get('uk', {}).keys())

print(f'Liczba kluczy:')
print(f'  PL: {len(pl_keys)}')
print(f'  UK: {len(uk_keys)}')

missing = sorted(pl_keys - uk_keys)
if missing:
    print(f'\nBrakujące klucze w ukraińskim ({len(missing)}):')
    for key in missing:
        pl_value = data['pl'][key]
        print(f'\n  "{key}": "{pl_value}",')
else:
    print('\n✓ Ukraiński słownik jest kompletny!')
