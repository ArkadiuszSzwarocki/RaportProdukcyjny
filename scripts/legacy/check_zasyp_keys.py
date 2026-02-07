#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź klucze dla Zasyp i Workowanie"""
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

# Szukane klucze
keys = ['zasyp', 'workowanie', 'brak_planow_zasyp', 'brak_planow_workowanie', 'data_zasypu', 'zrobiono_zasypie']

print('CHECK KEYS FOR ZASYP/WORKOWANIE:')
missing = []
for k in keys:
    found = k in trans['pl']
    status = '✓' if found else '✗'
    if found:
        print(f'{status} {k}')
        print(f'   PL: {trans["pl"][k]}')
        print(f'   UK: {trans["uk"][k]}')
    else:
        missing.append(k)
        print(f'{status} {k}: MISSING')

if missing:
    print(f'\nMISSING KEYS: {missing}')
