#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# Ostatnie 85 tekstów do dodania
remaining = {
    # Sekcje UI testowe i specjalne
    "agro": {"pl": "AGRO", "uk": "AGRO", "en": "AGRO"},
    "anuluj_btn": {"pl": "ANULUJ", "uk": "СКАСУВАТИ", "en": "CANCEL"},
    "big_bag_colon": {"pl": "Big Bag:", "uk": "Біг-бег:", "en": "Big Bag:"},
    "bigbag": {"pl": "BigBag", "uk": "Біг-бег", "en": "BigBag"},
    "bottom_sheet": {"pl": "Bottom sheet", "uk": "Нижня панель", "en": "Bottom sheet"},
    "center_modal_formularz": {"pl": "Center modal: Formularz", "uk": "Центральне модальне: Форма", "en": "Center modal: Form"},
    "center_modal_powiadomienie": {"pl": "Center modal: Powiadomienie", "uk": "Центральне модальне: Повідомлення", "en": "Center modal: Notification"},
    "co_mozesz_zrobic": {"pl": "Co możesz zrobić:", "uk": "Що ви можете зробити:", "en": "What you can do:"},
    "diagnostics": {"pl": "Diagnostics", "uk": "Діагностика", "en": "Diagnostics"},
    "diagnoza_brak": {"pl": "Diagnoza: brak", "uk": "Діагностика: відсутня", "en": "Diagnosis: none"},
    "do_rozliczenia": {"pl": "Do rozliczenia", "uk": "До розрахунку", "en": "To settle"},
    "dodaj_do_listy": {"pl": "Dodaj do listy", "uk": "Додати до списку", "en": "Add to list"},
    "dodaj_komentarz": {"pl": "Dodaj komentarz...", "uk": "Додайте коментар...", "en": "Add comment..."},
    "dodaj_konto_nowe": {"pl": "Dodaj nowe konto", "uk": "Додати новий облік", "en": "Add new account"},
    "dodajesz_palete": {"pl": "Dodajesz paletę", "uk": "Додаєте палету", "en": "You are adding a pallet"},
    "dodajesz_szarze": {"pl": "Dodajesz szarże", "uk": "Додаєте партію", "en": "You are adding a batch"},
    "dokumenty_jakosciowe": {"pl": "Dokumenty jakościowe", "uk": "Документи якості", "en": "Quality documents"},
    "drawer_left": {"pl": "Drawer (left)", "uk": "Панель (ліворуч)", "en": "Drawer (left)"},
    "drawer_lewo": {"pl": "Drawer (lewo)", "uk": "Панель (ліворуч)", "en": "Drawer (left)"},
    "drawer_prawo": {"pl": "Drawer (prawo)", "uk": "Панель (праворуч)", "en": "Drawer (right)"},
    "drawer_right": {"pl": "Drawer (right)", "uk": "Панель (праворуч)", "en": "Drawer (right)"},
    "fullscreen_modal": {"pl": "Fullscreen modal", "uk": "Повноекранне модальне", "en": "Fullscreen modal"},
    "fullscreen_modal_pl": {"pl": "Fullscreen Modal", "uk": "Повноекранне модальне", "en": "Fullscreen Modal"},
    "inline_html": {"pl": "Inline HTML", "uk": "Вбудований HTML", "en": "Inline HTML"},
    "inline_html_data": {"pl": "Inline HTML (data-slide-html)", "uk": "Вбудований HTML (data-slide-html)", "en": "Inline HTML (data-slide-html)"},
    "inne": {"pl": "Inne", "uk": "Інші", "en": "Other"},
    "jakosc_zlecenia_full": {"pl": "Jakość — zlecenia", "uk": "Якість — замовлення", "en": "Quality — Orders"},
    "krok_1_colon": {"pl": "KROK 1:", "uk": "КРОК 1:", "en": "STEP 1:"},
    "krok_2_colon": {"pl": "KROK 2:", "uk": "КРОК 2:", "en": "STEP 2:"},
    "krok_3_colon": {"pl": "KROK 3:", "uk": "КРОК 3:", "en": "STEP 3:"},
    "kalendarz_godzin_full": {"pl": "Kalendarz godzin (miesiąc)", "uk": "Календар годин (місяць)", "en": "Hours Calendar (month)"},
    "legenda_colon": {"pl": "Legenda:", "uk": "Легенда:", "en": "Legend:"},
    "lista_zlecen_jakosc": {"pl": "Lista zleceń oznaczonych jako jakość (dezynfekcja, dokumentacja laboratorium itp.).", "uk": "Список замовлень позначених як якість (дезінфекція, документація лабораторії тощо).", "en": "List of orders marked as quality (disinfection, laboratory documentation, etc.)."},
    "logi_systemowe": {"pl": "Logi Systemowe", "uk": "Системні журнали", "en": "System Logs"},
    "logowanie_agronetzwerk": {"pl": "Logowanie - AgroNetzwerk", "uk": "Вхід - AgroNetzwerk", "en": "Login - AgroNetzwerk"},
    "mes": {"pl": "MES", "uk": "МЕС", "en": "MES"},
    "mozesz_umieścić": {"pl": "Możesz tutaj umieścić formularz lub treść testową.", "uk": "Ви можете помістити тут форму або тестовий вміст.", "en": "You can place a form or test content here."},
    "podaj_liczbe_uszkodzonych": {"pl": "Podaj liczbę uszkodzonych worków", "uk": "Вкажіть кількість пошкоджених мішків", "en": "Enter number of damaged bags"},
    "pokaz_toast": {"pl": "Pokaż toast", "uk": "Показати сповіщення", "en": "Show toast"},
    "popover_przyklad": {"pl": "Popover (przykład)", "uk": "Спливаюче вікно (приклад)", "en": "Popover (example)"},
    "powrot_planista": {"pl": "Powrót do Planisty", "uk": "Повернення до Планувальника", "en": "Return to Planner"},
    "problem_colon": {"pl": "Problem:", "uk": "Проблема:", "en": "Problem:"},
    "produkcja": {"pl": "Produkcja", "uk": "Виробництво", "en": "Production"},
    "przykladowa_tresc": {"pl": "Przykładowa treść.", "uk": "Приклад вмісту.", "en": "Sample content."},
    "quick_popup": {"pl": "Quick popup (always works)", "uk": "Швидке спливаюче вікно (завжди працює)", "en": "Quick popup (always works)"},
    "rrrr_mm_dd": {"pl": "RRRR-MM-DD", "uk": "РРРР-ММ-ДД", "en": "YYYY-MM-DD"},
    "slide_duza_tresc": {"pl": "Slide: Duża treść", "uk": "Слайд: Великий вміст", "en": "Slide: Large content"},
    "slide_formularz": {"pl": "Slide: Formularz", "uk": "Слайд: Форма", "en": "Slide: Form"},
    "slide_potwierdzenie": {"pl": "Slide: Potwierdzenie", "uk": "Слайд: Підтвердження", "en": "Slide: Confirmation"},
    "strona": {"pl": "Strona", "uk": "Сторінка", "en": "Page"},
    "system": {"pl": "System", "uk": "Система", "en": "System"},
    "to_jest_zawartosc": {"pl": "To jest zawartość wstawiona przez atrybut", "uk": "Це вміст, вставлений за допомогою атрибута", "en": "This is content inserted by attribute"},
    "to_okno_dziala": {"pl": "To okno działa globalnie przez", "uk": "Це вікно працює глобально через", "en": "This window works globally through"},
    "towar_poprzednich_dni": {"pl": "Towar z poprzednich dni dostępny do spakowania", "uk": "Товар з попередніх днів доступний для упаковки", "en": "Goods from previous days available for packing"},
    "tu_mozesz_zarzadzac": {"pl": "Tu możesz zarządzać dostępem ról do stron aplikacji oraz ustawić, czy dostęp ma być tylko do odczytu.", "uk": "Тут ви можете керувати доступом ролей до сторінок додатків та встановити, чи доступ має бути лише для читання.", "en": "Here you can manage role access to application pages and set whether access should be read-only."},
    "twoje_konto_nie_powiazane": {"pl": "Twoje konto nie jest powiązane z rekordem pracownika. Skontaktuj się z administratorem.", "uk": "Ваш облік не пов'язаний із записом працівника. Зверніться до адміністратора.", "en": "Your account is not linked to an employee record. Contact your administrator."},
    "tymczasowe_haslo": {"pl": "Tymczasowe hasło", "uk": "Тимчасовий пароль", "en": "Temporary password"},
    "typ_produkcji_colon": {"pl": "Typ produkcji:", "uk": "Тип виробництва:", "en": "Type of production:"},
    "typy_przegladany": {"pl": "Typy — przeglądany", "uk": "Типи — переглянуто", "en": "Types — viewed"},
    "uwaga_delegacji": {"pl": "Uwaga: slide-over wykorzystuje mechanizm globalnej delegacji kliknięć. Atrybuty:", "uk": "Увага: slide-over використовує механізм глобальної делегації натисків. Атрибути:", "en": "Note: slide-over uses global click delegation mechanism. Attributes:"},
    "uwagi_colon": {"pl": "Uwagi:", "uk": "Замітки:", "en": "Notes:"},
    "wybierz_date_domyslnie": {"pl": "Wybierz datę (domyślnie dzisiaj)", "uk": "Виберіть дату (за замовчуванням сьогодні)", "en": "Select date (default today)"},
    "wybierz_pracownika_do_przeglądu": {"pl": "Wybierz pracownika do przeglądu", "uk": "Виберіть працівника для перегляду", "en": "Select employee for review"},
    "zagniezdzone": {"pl": "Zagnieżdżone", "uk": "Вкладені", "en": "Nested"},
    "zagniezdzone_html": {"pl": "Zagnieżdżone HTML", "uk": "Вкладений HTML", "en": "Nested HTML"},
    "zakonczono_colon": {"pl": "Zakończono:", "uk": "Завершено:", "en": "Completed:"},
    "zarzadzanie_produkcja_wszystkie": {"pl": "Zarządzanie Produkcją (Wszystkie Sekcje)", "uk": "Управління виробництвом (усі секції)", "en": "Production Management (All Sections)"},
    "pełnoekranowe_okno": {"pl": "Pełnoekranowe okno.", "uk": "Повноекранне вікно.", "en": "Fullscreen window."},
    "oblocenie_450": {"pl": "Obłożenie Zmiany (450 min)", "uk": "Навантаження зміни (450 хв)", "en": "Shift Load (450 min)"},
    "opcotwórz_PRje": {"pl": "Opcotwórz PRje", "uk": "Відкрити PR", "en": "Open PR"},
    "opis_opcjonalnie_colon": {"pl": "Opis (opcjonalnie):", "uk": "Опис (опціонально):", "en": "Description (optional):"},
    "opisz_problem_trzy": {"pl": "Opisz problem...", "uk": "Опишіть проблему...", "en": "Describe problem..."},
}

# Załaduj istniejące tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

before_count = len(translations['pl'])

# Dodaj nowe tłumaczenia
for key, values in remaining.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

after_count = len(translations['pl'])
print(f"✓ Dodano {after_count - before_count} nowych tłumaczeń")
print(f"  Przed: {before_count} kluczy")
print(f"  Po:    {after_count} kluczy")
print(f"\nRazem: PL={len(translations['pl'])}, UK={len(translations['uk'])}, EN={len(translations['en'])}")
