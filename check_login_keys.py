#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    t = json.load(f)

keys = ['zaloguj_sie', 'login', 'haslo', 'wejdz', 'wpisz_login', 'wpisz_haslo']
print("Klucze na stronie login:")
for k in keys:
    exists = k in t['pl']
    if exists:
        print(f"  ✓ {k}: PL={t['pl'][k]}, UK={t['uk'][k]}")
    else:
        print(f"  ✗ {k}: BRAK")
