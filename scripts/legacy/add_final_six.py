#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import re

# Załaduj istniejące
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

before_count = len(translations['pl'])

# Ostatnie 6 - ze zmienionymi kluczami aby je rozróżnić
final_six = {
    "bigbag_v2": {"pl": "BigBag", "uk": "Біг-бег", "en": "BigBag"},
    "brak_palet_czekajacych": {"pl": "Brak palet oczekujących na zatwierdzenie.", "uk": "Немає паліт, які чекають на затвердження.", "en": "No pallets awaiting approval."},
    "brak_planu_v2": {"pl": "Brak planu.", "uk": "Немає плану.", "en": "No plan."},
    "dodaj_v2": {"pl": "Dodaj", "uk": "Додати", "en": "Add"},
    "plan_wagowy_v2": {"pl": "Plan Wagowy", "uk": "План зважування", "en": "Weight Plan"},
    "realizacja_planu_v2": {"pl": "Realizacja Planu", "uk": "Реалізація плану", "en": "Plan Implementation"},
}

# Dodaj 
for key, values in final_six.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

after_count = len(translations['pl'])
print(f"✓ Dodano ostatnie {after_count - before_count} tłumaczeń")
print(f"  Razem: {after_count} kluczy\n")

# Wyświetl statystykę
print(f"Podsumowanie tłumaczeń:")
print(f"  PL: {len(translations['pl'])} kluczy")
print(f"  UK: {len(translations['uk'])} kluczy")
print(f"  EN: {len(translations['en'])} kluczy")
