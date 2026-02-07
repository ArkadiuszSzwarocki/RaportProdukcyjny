#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
with open('config/translations.json', 'r', encoding='utf-8') as f:
    t = json.load(f)
print(f'✓ Total keys: {len(t["pl"])}')
print('✓ KEY TRANSLATIONS:')
for k in ['hala_produkcyjna', 'sekcja', 'zasyp', 'workowanie']:
    if k in t['pl']:
        print(f'  ✓ {k}')
        print(f'     PL: {t["pl"][k]}')
        print(f'     UK: {t["uk"][k]}')
print('')
print('✓ NEXTQ STEPS:')
print('  1. Ctrl+Shift+R (hard refresh browser)')
print('  2. Or restart Flask app')
print('  3. Add ?lang=uk to URL')
