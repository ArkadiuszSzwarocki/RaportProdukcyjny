#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# Załaduj plik z UTF-8
with open('config/translations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

pl_keys = set(data.get('pl', {}).keys())
uk_keys = set(data.get('uk', {}).keys())

print(f'=== Porównanie kluczy ===')
print(f'PL: {len(pl_keys)} kluczy')
print(f'UK: {len(uk_keys)} kluczy')

# Klucze w PL ale nie w UK
missing_in_uk = sorted(pl_keys - uk_keys)
if missing_in_uk:
    print(f'\n⚠️  Brakujące w ukraińskim ({len(missing_in_uk)}):')
    for key in missing_in_uk:
        print(f'  • {key}: {data["pl"][key]}')
else:
    print(f'\n✓ Ukraiński ma wszystkie klucze!')

# Klucze w UK ale nie w PL
extra_in_uk = sorted(uk_keys - pl_keys)
if extra_in_uk:
    print(f'\n⚠️  Dodatkowe w ukraińskim ({len(extra_in_uk)}):')
    for key in extra_in_uk:
        print(f'  • {key}: {data["uk"][key]}')
