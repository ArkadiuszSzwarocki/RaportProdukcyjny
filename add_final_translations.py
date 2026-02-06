#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# Ostatnie 16 tekstów
final_batch = {
    "bigbag": {"pl": "BigBag", "uk": "Біг-бег", "en": "BigBag"},
    "brak_palet_oczekujacych": {"pl": "Brak palet oczekujących na zatwierdzenie.", "uk": "Немає паліт, які чекають на затвердження.", "en": "No pallets awaiting approval."},
    "brak_planu": {"pl": "Brak planu.", "uk": "Немає плану.", "en": "No plan."},
    "brak_potwierdzone_palet": {"pl": "Brak potwierdzone palet.", "uk": "Немає затверджених паліт.", "en": "No confirmed pallets."},
    "brak_zlecen_w_bazie": {"pl": "Brak zleceń w bazie.", "uk": "Немає замовлень у базі даних.", "en": "No orders in database."},
    "data_planu_colon": {"pl": "Data planu:", "uk": "Дата плану:", "en": "Plan date:"},
    "data_colon": {"pl": "Data:", "uk": "Дата:", "en": "Date:"},
    "dodaj": {"pl": "Dodaj", "uk": "Додати", "en": "Add"},
    "dodaj_konto": {"pl": "Dodaj konto", "uk": "Додати облік", "en": "Add account"},
    "dodaj_palete_btn": {"pl": "Dodaj paletę", "uk": "Додати палету", "en": "Add pallet"},
    "plan_wagowy": {"pl": "Plan Wagowy", "uk": "План зважування", "en": "Weight Plan"},
    "realizacja_planu": {"pl": "Realizacja Planu", "uk": "Реалізація плану", "en": "Plan Implementation"},
    "start_btn": {"pl": "START", "uk": "ПОЧАТОК", "en": "START"},
    "stop_btn": {"pl": "STOP", "uk": "СТОП", "en": "STOP"},
    "typy_przeglądany": {"pl": "Typy — przeglądany", "uk": "Типи — переглянуто", "en": "Types — viewed"},
    "zakonczono_colon_final": {"pl": "Zakończone:", "uk": "Завершено:", "en": "Completed:"},
}

# Załaduj istniejące
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

before_count = len(translations['pl'])

# Dodaj
for key, values in final_batch.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

after_count = len(translations['pl'])
print(f"✓ Dodano ostatnie {after_count - before_count} tłumaczeń")
print(f"  Przed: {before_count} kluczy")
print(f"  Po:    {after_count} kluczy")
print(f"\nRazem: PL={len(translations['pl'])}, UK={len(translations['uk'])}, EN={len(translations['en'])}")
