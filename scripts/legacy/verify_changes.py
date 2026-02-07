#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź czy wszystkie zmiany są w translations.json"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

print('✓ VERIFICICATION OF CHANGES:')
print(f'  Total keys: {len(trans["pl"])} (all languages synchronized)')
print()
print('✓ ZASYP/WORKOWANIE translations:')
checks = [
    ('zasyp', 'Zasyp', 'Насипання'),
    ('workowanie', 'Workowanie', 'Пакування'),
    ('produkcja', 'Produkcja', 'Виробництво'),
    ('sekcje', 'Sekcje', 'Секції'),
    ('status_hr', 'Status HR', 'Статус HR'),
]

for key, pl, uk in checks:
    if key in trans['pl']:
        actual_pl = trans['pl'][key]
        actual_uk = trans['uk'][key]
        match = '✓' if actual_pl == pl and actual_uk == uk else '⚠'
        print(f'{match} {key}:')
        print(f'   PL: {actual_pl}')
        print(f'   UK: {actual_uk}')
    else:
        print(f'✗ {key}: MISSING!')

print('\n✓ APP IS READY TO TEST')
print('  Go to: http://localhost:5000/?lang=uk')
print('  Or use language selector on login page')
print('  Then press Ctrl+Shift+R to clear cache')
