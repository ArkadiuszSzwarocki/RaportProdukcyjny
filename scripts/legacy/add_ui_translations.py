#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# Te teksty będą dodane do translations.json
# Format: "key": {"pl": "...", "uk": "...", "en": "..."}

new_translations = {
    # Najważniejsze nagłówki i etykiety
    "produkt": {
        "pl": "Produkt",
        "uk": "Продукт",
        "en": "Product"
    },
    "godz": {
        "pl": "Godz.",
        "uk": "Год.",
        "en": "Hour"
    },
    "czas_awarii": {
        "pl": "Czas Awarii",
        "uk": "Час відмови",
        "en": "Failure Time"
    },
    "wykonanie_gotowe": {
        "pl": "Wykonanie (Gotowe)",
        "uk": "Виконання (Готово)",
        "en": "Execution (Done)"
    },
    "plan_wagowy": {
        "pl": "Plan Wagowy",
        "uk": "План ваги",
        "en": "Weight Plan"
    },
    "realizacja_planu": {
        "pl": "Realizacja Planu",
        "uk": "Виконання плану",
        "en": "Plan Execution"
    },
    "realizacja_celu": {
        "pl": "Realizacja Celu",
        "uk": "Досягнення мети",
        "en": "Target Achievement"
    },
    
    # Przycisamy i główne akcje
    "dodaj_palete": {
        "pl": "DODAJ PALETĘ",
        "uk": "ДОДАТИ ПАЛЕТУ",
        "en": "ADD PALLET"
    },
    "dodaj_szarze": {
        "pl": "DODAJ SZARŻĘ",
        "uk": "ДОДАТИ ПАРТІЮ",
        "en": "ADD BATCH"
    },
    "zatwierdz_wszystkie": {
        "pl": "Zatwierdź wszystkie",
        "uk": "Затвердити все",
        "en": "Approve All"
    },
    "zapisz_notatke": {
        "pl": "Zapisz notatkę",
        "uk": "Зберегти примітку",
        "en": "Save Note"
    },
    "pobierz_raport_dzisiaj": {
        "pl": "Pobierz raport z dzisiaj",
        "uk": "Завантажити звіт сьогодні",
        "en": "Download Today's Report"
    },
    "pobierz_z_wybranej_daty": {
        "pl": "Pobierz z wybranej daty",
        "uk": "Завантажити з вибраної дати",
        "en": "Download from Selected Date"
    },
    
    # Status i komunikaty
    "brak_notatek": {
        "pl": "Brak notatek dla tego dnia.",
        "uk": "Немає приміток на цей день.",
        "en": "No notes for this day."
    },
    "brak_danych": {
        "pl": "Brak danych.",
        "uk": "Немає даних.",
        "en": "No data."
    },
    "brak_planow_zasyp": {
        "pl": "Brak planów Zasyp na ten dzień.",
        "uk": "Немає планів Засипання на цей день.",
        "en": "No Fill plans for this day."
    },
    "brak_planow_workowanie": {
        "pl": "Brak planów Workowanie na ten dzień.",
        "uk": "Немає планів опрацювання на цей день.",
        "en": "No Processing plans for this day."
    },
    "brak_palet": {
        "pl": "Brak palet oczekujących na zatwierdzenie.",
        "uk": "Немає палет, що чекають затвердження.",
        "en": "No pallets awaiting approval."
    },
    "brak_pracownikow": {
        "pl": "Brak pracowników.",
        "uk": "Немає працівників.",
        "en": "No employees."
    },
    
    # Informacyjne
    "instrukcja": {
        "pl": "Instrukcja:",
        "uk": "Інструкція:",
        "en": "Instructions:"
    },
    "krok_1": {
        "pl": "Krok 1",
        "uk": "Крок 1",
        "en": "Step 1"
    },
    "krok_2": {
        "pl": "Krok 2",
        "uk": "Крок 2",
        "en": "Step 2"
    },
    "krok_3": {
        "pl": "Krok 3",
        "uk": "Крок 3",
        "en": "Step 3"
    },
    "nr": {
        "pl": "Nr",
        "uk": "№",
        "en": "No."
    },
    "sekcja": {
        "pl": "Sekcja:",
        "uk": "Секція:",
        "en": "Section:"
    },
    "typ": {
        "pl": "Typ",
        "uk": "Тип",
        "en": "Type"
    },
    "numer": {
        "pl": "Numer",
        "uk": "Номер",
        "en": "Number"
    },
    "imie_i_nazwisko": {
        "pl": "Imię i nazwisko",
        "uk": "Ім'я та прізвище",
        "en": "First and Last Name"
    },
    
    # Kategorie/Sekcje
    "bufor": {
        "pl": "Bufor",
        "uk": "Буфер",
        "en": "Buffer"
    },
    "hala_agro": {
        "pl": "Hala Agro",
        "uk": "Зал AGRO",
        "en": "Agro Hall"
    },
    "lider_agro": {
        "pl": "Lider AGRO:",
        "uk": "Лідер AGRO:",
        "en": "AGRO Leader:"
    },
    "lider_psd": {
        "pl": "Lider PSD:",
        "uk": "Лідер PSD:",
        "en": "PSD Leader:"
    },
    
    # Komunikaty błędów
    "cos_poszlo_nie_tak": {
        "pl": "Coś poszło nie tak...",
        "uk": "Щось пішло не так...",
        "en": "Something went wrong..."
    },
    "blad_ladowania": {
        "pl": "Błąd ładowania notatek",
        "uk": "Помилка завантаження приміток",
        "en": "Error loading notes"
    },
    "skontaktuj_sie_z_admin": {
        "pl": "Jeśli problem będzie się powtarzać, skontaktuj się z administratorem",
        "uk": "Якщо проблема не зникне, зв'яжіться з адміністратором",
        "en": "If the problem persists, contact your administrator"
    },
    
    # Waluta i jednostki
    "kg": {
        "pl": "kg",
        "uk": "кг",
        "en": "kg"
    },
    "kg_jednostka": {
        "pl": "kg",
        "uk": "кг",
        "en": "kg"
    },
    "procent": {
        "pl": "%",
        "uk": "%",
        "en": "%"
    },
    
    # Formularze
    "wymagane": {
        "pl": "[Wymagane]",
        "uk": "[Обов'язково]",
        "en": "[Required]"
    },
    "opcjonalnie": {
        "pl": "(opcjonalnie)",
        "uk": "(опціонально)",
        "en": "(optional)"
    },
    
    # Miesiące i dni
    "miesiac": {
        "pl": "Miesiąc",
        "uk": "Місяць",
        "en": "Month"
    },
    "rok": {
        "pl": "Rok",
        "uk": "Рік",
        "en": "Year"
    },
    "podsumowanie": {
        "pl": "Podsumowanie",
        "uk": "Резюме",
        "en": "Summary"
    },
}

# Załaduj istniejące tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

# Dodaj nowe tłumaczenia
for key, values in new_translations.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

print(f"✓ Dodano {len(new_translations)} nowych tłumaczeń")
print(f"  Razem kluczy: PL={len(translations['pl'])}, UK={len(translations['uk'])}, EN={len(translations['en'])}")
