#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź brakujące klucze dla Zasyp i Workowanie"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

# Klucze których potrzebujemy
required = {
    'produkcja': ('Produkcja', 'Виробництво', 'Production'),
    'sekcje': ('Sekcje', 'Секції', 'Sections'),
    'magazyn': ('Magazyn', 'Склад', 'Warehouse'),
    'hala_agro': ('Hala Agro', 'Зерновий корпус', 'Agro Hall'),
    'status_hr': ('Status HR', 'Статус HR', 'HR Status'),
}

print('SPRAWDZANIE BRAKUJĄCYCH KLUCZY:')
missing = []
for k, vals in required.items():
    if k in trans['pl']:
        print(f'✓ {k}')
    else:
        missing.append(k)
        print(f'✗ {k} MISSING - dodaj: {vals}')

if missing:
    print(f'\nDODAJ KLUCZE:')
    for k, vals in required.items():
        if k in missing:
            trans['pl'][k] = vals[0]
            trans['uk'][k] = vals[1]
            trans['en'][k] = vals[2]
    
    with open('config/translations.json', 'w', encoding='utf-8') as f:
        json.dump(trans, f, ensure_ascii=False, indent=2)
    print(f'✓ Dodano {len(missing)} brakujących kluczy')
else:
    print('✓ Wszystkie klucze są dostępne')
