#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź czy wszystkie tłumaczenia są zsynchronizowane"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)
    
print(f'Tłumaczenia w translations.json:')
print(f'  Polskie:    {len(trans["pl"])} kluczy')
print(f'  Ukrainskie: {len(trans["uk"])} kluczy')
print(f'  Angielskie: {len(trans["en"])} kluczy')

# Sprawdź czy nowe klucze są
print(f'\nSprawdzenie nowych tłumaczeń:')
new_keys = ['wewnetrzny_blad', 'do_przyjecia', 'przyjeta', 'zamknieta', 'brak_palet_czekajacych']
for k in new_keys:
    if k in trans['pl']:
        print(f'✓ {k}: PL="{trans["pl"][k]}" UK="{trans["uk"][k]}"')
    else:
        print(f'✗ Brak: {k}')
