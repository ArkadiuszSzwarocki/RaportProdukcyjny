#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dodaj pozostałe UI teksty do translations.json"""

import json
import re

# Zidentyfikowane najważniejsze teksty UI do przetłumaczenia
new_translations = {
    # 500.html - Error messages
    "napotkalismy_blad": {
        "pl": "Napotkaliśmy błąd podczas przetwarzania Twojego żądania.",
        "uk": "Під час обробки вашого запиту сталася помилка.",
        "en": "We encountered an error while processing your request."
    },
    "szczegoly_zalogowane": {
        "pl": "Szczegóły błędu zostały zalogowane i przekazane zespołowi technicznemu.",
        "uk": "Деталі помилки були залоговані та передані техічній команді.",
        "en": "Error details have been logged and sent to the technical team."
    },
    
    # Dashboard navigation
    "poprzedni_dzien": {
        "pl": "Poprzedni dzień",
        "uk": "Попередній день",
        "en": "Previous day"
    },
    "nastepny_dzien": {
        "pl": "Następny dzień",
        "uk": "Наступний день",
        "en": "Next day"
    },
    
    # Dashboard badges and status
    "do_przyjecia": {
        "pl": "Do przyjęcia",
        "uk": "До прийняття",
        "en": "To accept"
    },
    "przyjeta": {
        "pl": "Przyjęta",
        "uk": "Прийнята",
        "en": "Accepted"
    },
    "zamknieta": {
        "pl": "Zamknięta",
        "uk": "Закрита",
        "en": "Closed"
    },
    
    # Dashboard section titles
    "wznow_zlecenia_z_wczoraj": {
        "pl": "Wznów zlecenia z wczoraj",
        "uk": "Відновити замовлення вчора",
        "en": "Resume orders from yesterday"
    },
    
    # Dashboard global actions
    "zakonczy_zmiane_i_pobierz_raporty": {
        "pl": "Zakończ zmianę i pobierz raporty",
        "uk": "Завершити зміну та завантажити звіти",
        "en": "Complete shift and download reports"
    },
    "wyslij_raport_mailem": {
        "pl": "Wyślij raport mailem",
        "uk": "Надіслати звіт електронною поштою",
        "en": "Send report by email"
    },
    "zakonczy_zmiane_i_zapisz_raport": {
        "pl": "Zakończ zmianę i Zapisz Raport",
        "uk": "Завершити зміну та Зберегти Звіт",
        "en": "Complete shift and Save Report"
    },
    
    # HR/Absence panels
    "ostatnie_nieobecnosci": {
        "pl": "Ostatnie Nieobecności (30 dni)",
        "uk": "Останні Відсутності (30 днів)",
        "en": "Recent Absences (30 days)"
    },
    "brak_wpisow": {
        "pl": "Brak wpisów z ostatnich 30 dni.",
        "uk": "Немає записів за останні 30 днів.",
        "en": "No entries from the last 30 days."
    },
    "planowane_urlopy": {
        "pl": "Planowane Urlopy (Następne 60 dni)",
        "uk": "Заплановані Відпустки (Наступні 60 днів)",
        "en": "Scheduled Vacations (Next 60 days)"
    },
    "brak_planowanych_urlopow": {
        "pl": "Brak planowanych urlopów.",
        "uk": "Немає заплануваних відпусток.",
        "en": "No scheduled vacations."
    },
    "zatwierdzenia_wnioskow": {
        "pl": "Zatwierdzenia Wniosków",
        "uk": "Затвердження Запитів",
        "en": "Request Approvals"
    },
    "pracownik_typ_okres_powod": {
        "pl": "Pracownik | Typ | Okres | Powód",
        "uk": "Працівник | Тип | Період | Причина",
        "en": "Employee | Type | Period | Reason"
    },
    "odrzuc": {
        "pl": "Odrzuć",
        "uk": "Відхилити",
        "en": "Reject"
    },
    "brak_oczekujacych_wnioskow": {
        "pl": "Brak oczekujących wniosków lub brak uprawnień.",
        "uk": "Немає очікуючих запитів або немає прав доступу.",
        "en": "No pending requests or insufficient permissions."
    },
    
    # Obsada page
    "obsada_pelna_strona": {
        "pl": "Obsada - pełna strona",
        "uk": "Штат - повна сторінка",
        "en": "Staffing - full page"
    },
    "usun_z_obsady": {
        "pl": "Usuń z obsady",
        "uk": "Видалити зі штату",
        "en": "Remove from staffing"
    },
    
    # Szarža form
    "nowa_sarzha": {
        "pl": "Nowa Szarża",
        "uk": "Нова Партія",
        "en": "New Batch"
    },
    
    # Koniec zlecenia
    "czy_zgłaszasz_uszkodzone_worki": {
        "pl": "Czy zgłaszasz uszkodzone worki?",
        "uk": "Чи повідомляєте про пошкоджені мішки?",
        "en": "Are you reporting damaged bags?"
    },
    "z_iloscia": {
        "pl": "z ilością",
        "uk": "з кількістю",
        "en": "with quantity"
    },
    "podaj_liczbe_uszkodzonych_workow": {
        "pl": "Podaj liczbę uszkodzonych worków",
        "uk": "Вкажіть кількість пошкоджених мішків",
        "en": "Provide the number of damaged bags"
    },
    
    # Slide-over message
    "czy_wznowic_zlecenie": {
        "pl": "Czy wznowić zlecenie",
        "uk": "Чи відновити замовлення",
        "en": "Resume order"
    },
    
    # Report download
    "krok_3_przeciagnij_pliki": {
        "pl": "KROK 3: Przeciągnij pobrane pliki do okna wiadomości.",
        "uk": "КРОК 3: Перетягніть завантажені файли до вікна повідомлення.",
        "en": "STEP 3: Drag the downloaded files to the message window."
    },
    "raport_pobrany_pomyslnie": {
        "pl": "Raport pobrany pomyślnie!",
        "uk": "Звіт успішно завантажено!",
        "en": "Report downloaded successfully!"
    },
    "prosze_wybrac_date": {
        "pl": "Proszę wybrać datę!",
        "uk": "Будь ласка, виберіть дату!",
        "en": "Please select a date!"
    },
    "wysylanie": {
        "pl": "Wysyłanie...",
        "uk": "Відправка...",
        "en": "Sending..."
    },
    "blad_serwera": {
        "pl": "Błąd serwera",
        "uk": "Помилка сервера",
        "en": "Server error"
    },
    "blad_sieci": {
        "pl": "Błąd sieci",
        "uk": "Помилка мережі",
        "en": "Network error"
    },
    
    # Zarzad page
    "statystyki_pracownikow_hr": {
        "pl": "Statystyki Pracowników (HR)",
        "uk": "Статистика Працівників (HR)",
        "en": "Employee Statistics (HR)"
    },
    "przyczyny_przestojow": {
        "pl": "Przyczyny Przestojów",
        "uk": "Причини Простоїв",
        "en": "Reasons for Downtime"
    },
    "lacznie": {
        "pl": "Łącznie",
        "uk": "Всього",
        "en": "Total"
    },
    "dni_pracy": {
        "pl": "Dni Pracy",
        "uk": "Дні роботи",
        "en": "Working days"
    },
    "nadgodziny": {
        "pl": "Nadgodziny",
        "uk": "Понаднормові",
        "en": "Overtime"
    },
    
    # Wyjaśnienie
    "wyjasnienie_rozbieznosci": {
        "pl": "Wyjaśnienie rozbieżności",
        "uk": "Пояснення невідповідностей",
        "en": "Explanation of discrepancies"
    },
    
    # Admin settings
    "mozesz_ustawic_tymczasowe_haslo": {
        "pl": "Możesz ustawić tymczasowe hasło lub poprosić użytkowników o zmianę.",
        "uk": "Ви можете встановити тимчасовий пароль або попросити користувачів змінити його.",
        "en": "You can set a temporary password or ask users to change it."
    },
    "tymczasowe_haslo": {
        "pl": "Tymczasowe hasło",
        "uk": "Тимчасовий пароль",
        "en": "Temporary password"
    },
    "nie_wszystko_przetlumaczone": {
        "pl": "Nie wszystko przetłumaczone",
        "uk": "Не все перекладено",
        "en": "Not everything translated"
    },
    "treść_zadania_produkt": {
        "pl": "Treść zadania / Produkt",
        "uk": "Зміст завдання / Продукт",
        "en": "Task content / Product"
    },
    "ilosc": {
        "pl": "Ilość",
        "uk": "Кількість",
        "en": "Quantity"
    },
    "dodaj_palete": {
        "pl": "+ DODAJ PALETĘ",
        "uk": "+ ДОДАТИ ПІДДОН",
        "en": "+ ADD PALLET"
    },
    "zakonczy_zlecenie": {
        "pl": "■ ZAKOŃCZ ZLECENIE",
        "uk": "■ ЗАВЕРШИТИ ЗАМОВЛЕННЯ",
        "en": "■ COMPLETE ORDER"
    },
    "pokaz_ukryj_kolejke": {
        "pl": "🔽 POKAŻ / UKRYJ KOLEJKĘ ZLECEŃ",
        "uk": "🔽 ПОКАЗАТИ / СХОВАТИ ЧЕРГУ ЗАМОВЛЕНЬ",
        "en": "🔽 SHOW / HIDE ORDER QUEUE"
    },
    "brak_planu_na_dzis": {
        "pl": "Brak planu na dziś.",
        "uk": "Немає плану на сьогодні.",
        "en": "No plan for today."
    },
    "zacznij_przejscie": {
        "pl": "🔁 ZACZNIJ PRZEJŚCIE",
        "uk": "🔁 ПОЧАТИ ПЕРЕХОДУ",
        "en": "🔁 START CHANGEOVER"
    },
    "awarie_usterki_nieobecnosci": {
        "pl": "Awarie / Usterki / Nieobecności",
        "uk": "Поломки / Несправності / Відсутності",
        "en": "Failures / Malfunctions / Absences"
    },
    "nieobecnosc": {
        "pl": "Nieobecność",
        "uk": "Відсутність",
        "en": "Absence"
    },
    "rola_uzytkownika": {
        "pl": "Rola użytkownika",
        "uk": "Роль користувача",
        "en": "User role"
    },
    "usun_konto": {
        "pl": "Usuń konto",
        "uk": "Видалити обліковий запис",
        "en": "Delete account"
    },
    "slide_duza_tresc": {
        "pl": "Slide: Duża treść",
        "uk": "Слайд: Велика вміст",
        "en": "Slide: Large content"
    },
    "popover_przyklad": {
        "pl": "Popover (przykład)",
        "uk": "Поповер (приклад)",
        "en": "Popover (example)"
    },
    "status_wymaga_migracji": {
        "pl": "Status wymaga migracji - proszę wybrać nowy status z listy",
        "uk": "Статус вимагає міграції - будь ласка, виберіть новий статус зі списку",
        "en": "Status requires migration - please select a new status from the list"
    },
    "wybierz_date_domyslnie_dzisiaj": {
        "pl": "Wybierz datę (domyślnie dzisiaj)",
        "uk": "Виберіть дату (за замовчуванням сьогодні)",
        "en": "Select date (default today)"
    },
}

# Wczytaj istniejące tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    existing = json.load(f)

# Zlicz nowe pozycje
added = 0
skipped = 0

for key, translations in new_translations.items():
    if key not in existing:
        existing[key] = translations
        added += 1
        print(f"✓ Dodano: {key}")
    else:
        skipped += 1
        print(f"⊘ Już istnieje: {key}")

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)

print(f"\n{'='*50}")
print(f"✓ Dodano: {added} nowych kluczy")
print(f"⊘ Pominięto: {skipped} istniejących kluczy")
print(f"{'='*50}")

# Wydrukuj podsumowanie
keys = list(existing.keys())
print(f"RAZEM KLUCZY: {len(keys)}")
for lang in ['pl', 'uk', 'en']:
    count = sum(1 for v in existing.values() if lang in v)
    print(f"  {lang}: {count} kluczy")
