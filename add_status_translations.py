#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Przygotuj dynamiczne tłumaczenia status_map dla JS"""

import json

new_status_translations = {
    "status_zgloszony": {
        "pl": "Zgłoszony",
        "uk": "Оголошений",
        "en": "Reported"
    },
    "status_czeka_na_czesci": {
        "pl": "Czeka na części",
        "uk": "Чекає частини",
        "en": "Waiting for parts"
    },
    "status_zakończony": {
        "pl": "Zakończony",
        "uk": "Завершений",
        "en": "Completed"
    },
    "status_zamknięty": {
        "pl": "Zamknięty",
        "uk": "Закритий",
        "en": "Closed"
    },
    "status_w_trakcie_naprawy": {
        "pl": "W trakcie naprawy",
        "uk": "Під час ремонту",
        "en": "Under repair"
    },
}

# Wczytaj JSON
with open('config/translations.json', 'r', encoding='utf-8') as f:
    trans = json.load(f)

# Dodaj statusy
for key, values in new_status_translations.items():
    if key not in trans['pl']:
        trans['pl'][key] = values['pl']
        trans['uk'][key] = values['uk']
        trans['en'][key] = values['en']
        print(f"✓ Dodano: {key}")
    else:
        print(f"⊘ Już istnieje: {key}")

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(trans, f, ensure_ascii=False, indent=2)

print(f"\nRAZEM kluczy PL: {len(trans['pl'])}")
