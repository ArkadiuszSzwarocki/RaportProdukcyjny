#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dodaj brakujące tłumaczenia"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

# Nowe klucze
new_keys = {
    'kolejka_produkcyjna': ('Kolejka Produkcyjna', 'Черга виробництва', 'Production Queue'),
    'rejestr_przyjec': ('Rejestr Przyjęć', 'Реєстр прийомів', 'Reception Register'),
    'wczesniejsze_zlecenia': ('Wcześniejsze zlecenia', 'Попередні замовлення', 'Previous Orders'),
}

for key, vals in new_keys.items():
    if key not in trans['pl']:
        trans['pl'][key] = vals[0]
        trans['uk'][key] = vals[1]
        trans['en'][key] = vals[2]
        print(f'✓ Dodano: {key}')
    else:
        print(f'✓ Już istnieje: {key}')

with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(trans, f, ensure_ascii=False, indent=2)

print(f'\n✓ Total keys: {len(trans["pl"])}')
