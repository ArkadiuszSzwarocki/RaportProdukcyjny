#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dodaj tłumaczenie dla 'Hala Produkcyjna'"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

# Dodaj nowy klucz
trans['pl']['hala_produkcyjna'] = 'Hala Produkcyjna'
trans['uk']['hala_produkcyjna'] = 'Хала Виробництва'
trans['en']['hala_produkcyjna'] = 'Production Hall'

with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(trans, f, ensure_ascii=False, indent=2)

print(f'✓ Dodano klucz hala_produkcyjna')
print(f'  PL: {trans["pl"]["hala_produkcyjna"]}')
print(f'  UK: {trans["uk"]["hala_produkcyjna"]}')
print(f'  Total: {len(trans["pl"])} kluczy')
