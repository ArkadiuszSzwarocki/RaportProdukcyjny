#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dodaj brakujące tłumaczenia
"""
import json
import re

# Brakujące teksty znalezione w szablonach
missing = {
    "wewnetrzny_blad": {"pl": "Wewnętrzny Błąd Serwera", "uk": "Внутрішня помилка сервера", "en": "Internal Server Error"},
    "co_mozesz_zrobic": {"pl": "Co możesz zrobić:", "uk": "Що ви можете зробити:", "en": "What you can do:"},
    "wroc": {"pl": "Wróć", "uk": "Повернутися", "en": "Go Back"},
    "opcotwórz_prje": {"pl": "Opcotwórz PRje", "uk": "Відкрити PR", "en": "Open PR"},
    "zarzadzanie_produkcja": {"pl": "Zarządzanie Produkcją (Wszystkie Sekcje)", "uk": "Управління виробництвом (усі секції)", "en": "Production Management (All Sections)"},
    "brak_zlecen_bazie": {"pl": "Brak zleceń w bazie.", "uk": "Немає замовлень у базі даних.", "en": "No orders in database."},
    "zarzadzanie_uzytkownikami": {"pl": "Zarządzanie użytkownikami", "uk": "Управління користувачами", "en": "User Management"},
    "usun_palete": {"pl": "Usuń paletę", "uk": "Видалити палету", "en": "Delete pallet"},
    "brak_palet_czekajacych": {"pl": "Brak palet oczekujących na zatwierdzenie.", "uk": "Немає паліт, які чекають на затвердження.", "en": "No pallets awaiting approval."},
    "do_przyjecia": {"pl": "Do przyjęcia", "uk": "До прийняття", "en": "To Accept"},
    "przyjeta": {"pl": "Przyjęta", "uk": "Прийнята", "en": "Accepted"},
    "zamknieta": {"pl": "Zamknięta", "uk": "Закрита", "en": "Closed"},
    "ladowanie": {"pl": "Ładowanie…", "uk": "Завантаження…", "en": "Loading..."},
    "podglad_produkcji": {"pl": "Podgląd produkcji dziennej (Zasyp / Workowanie)", "uk": "Перегляд щоденного виробництва (Засипання / Обробка)", "en": "Daily Production Preview (Pouring / Processing)"},
    "dodaj_palete": {"pl": "Dodaj paletę", "uk": "Додати палету", "en": "Add Pallet"},
    "edytuj_zgloszenie": {"pl": "Edytuj Zgłoszenie", "uk": "Редагувати звіт", "en": "Edit Report"},
    "edytuj_palete": {"pl": "Edytuj paletę", "uk": "Редагувати палету", "en": "Edit Pallet"},
    "jakosc_zlecenia": {"pl": "Jakość — zlecenia", "uk": "Якість — замовлення", "en": "Quality — Orders"},
    "lista_zlecen_jakosc": {"pl": "Lista zleceń oznaczonych jako jakość (dezynfekcja, dokumentacja laboratorium itp.).", "uk": "Список замовлень позначених як якість (дезінфекція, документація лабораторії тощо).", "en": "List of orders marked as quality (disinfection, laboratory documentation, etc.)."},
    "dokumenty_jakosciowe": {"pl": "Dokumenty jakościowe", "uk": "Документи якості", "en": "Quality Documents"},
    "brak_uszkodzonych": {"pl": "Jeśli brak uszkodzonych worków, wpisz", "uk": "Якщо пошкоджених мішків немає, введіть", "en": "If no damaged bags, enter"},
    "konto_nie_powiazane": {"pl": "Twoje konto nie jest powiązane z rekordem pracownika. Skontaktuj się z administratorem.", "uk": "Ваш облік не пов'язаний із записом працівника. Зверніться до адміністратора.", "en": "Your account is not linked to an employee record. Contact your administrator."},
    "typy_przeglądany": {"pl": "Typy — przeglądany", "uk": "Типи — переглянуто", "en": "Types — Viewed"},
    "kalendarz_godzin": {"pl": "Kalendarz godzin (miesiąc)", "uk": "Календар годин (місяць)", "en": "Hours Calendar (month)"},
    "oblegenie_zmiany": {"pl": "Obłożenie Zmiany (450 min)", "uk": "Навантаження зміни (450 хв)", "en": "Shift Load (450 min)"},
    "dodawanie_zlecen": {"pl": "Dodawanie wielu zleceń - Planista", "uk": "Додавання множинних замовлень - Планувальник", "en": "Adding Multiple Orders - Planner"},
    "zmiana_zamknieta": {"pl": "Zmiana Zamknięta Pomyślnie!", "uk": "Зміна успішно закрита!", "en": "Shift Closed Successfully!"},
    "pliki_powinny_pobrac": {"pl": "Pliki Excel i PDF powinny pobrać się automatycznie.", "uk": "Файли Excel і PDF повинні завантажитися автоматично.", "en": "Excel and PDF files should download automatically."},
    "kliknij_otworz_outlooka": {"pl": "Kliknij \"Otwórz Outlooka\".", "uk": "Натисніть \"Відкрити Outlook\".", "en": "Click \"Open Outlook\"."},
    "powod": {"pl": "Powód", "uk": "Причина", "en": "Reason"},
    "ilosc": {"pl": "Ilość", "uk": "Кількість", "en": "Quantity"},
    "zgloszenie_problem": {"pl": "Zgłoś Problem / Usterkę", "uk": "Будь ласка, повідомте про проблему /несправність", "en": "Report Problem / Issue"},
    "zawartość_atrybut": {"pl": "To jest zawartość wstawiona przez atrybut", "uk": "Це вміст, вставлений за допомогою атрибута", "en": "This is content inserted by attribute"},
    "zagniezdzenie_html": {"pl": "Zagnieżdżone HTML", "uk": "Вкладений HTML", "en": "Nested HTML"},
    "zagniedzne": {"pl": "Zagnieżdżone", "uk": "Вкладені", "en": "Nested"},
    "slide_duza_tresc": {"pl": "Slide: Duża treść", "uk": "Слайд: Великий вміст", "en": "Slide: Large content"},
    "pokaz_toast": {"pl": "Pokaż toast", "uk": "Показати сповіщення", "en": "Show toast"},
    "przykladowa_tresc": {"pl": "Przykładowa treść.", "uk": "Приклад вмісту.", "en": "Sample content."},
    "popover_przyklad": {"pl": "Popover (przykład)", "uk": "Спливаюче вікно (приклад)", "en": "Popover (example)"},
    "uwaga_slide_over": {"pl": "Uwaga: slide-over wykorzystuje mechanizm globalnej delegacji kliknięć. Atrybuty:", "uk": "Увага: slide-over використовує механізм глобальної делегації натисків. Атрибути:", "en": "Note: slide-over uses global click delegation mechanism. Attributes:"},
    "lub_wywolanie": {"pl": ", lub wywołanie", "uk": ", або виклик", "en": ", or call"},
    "okno_dziala_globalnie": {"pl": "To okno działa globalnie przez", "uk": "Це вікно працює глобально через", "en": "This window works globally through"},
    "formularz_tresc": {"pl": "Możesz tutaj umieścić formularz lub treść testową.", "uk": "Ви можете помістити тут форму або тестовий вміст.", "en": "You can place a form or test content here."},
    "pełnoekranowe_okno": {"pl": "Pełnoekranowe okno.", "uk": "Повноекранне вікно.", "en": "Fullscreen window."},
    "nowa_szarza": {"pl": "Nowa Szarża", "uk": "Нова партія", "en": "New Batch"},
    "wybierz_date": {"pl": "Wybierz datę (domyślnie dzisiaj)", "uk": "Виберіть дату (за замовчуванням сьогодні)", "en": "Select date (default today)"},
    "ustaw_wlasne_id": {"pl": "Ustaw własne ID", "uk": "Встановіть власний ID", "en": "Set custom ID"},
    "zarzadzanie_dostepem": {"pl": "Tu możesz zarządzać dostępem ról do stron aplikacji oraz ustawić, czy dostęp ma być tylko do odczytu.", "uk": "Тут ви можете керувати доступом ролей до сторінок додатків та встановити, чи доступ має бути лише для читання.", "en": "Here you can manage role access to application pages and set whether access should be read-only."},
    "powrot_panel": {"pl": "Powrót do panelu", "uk": "Повернення до панелі", "en": "Return to panel"},
    "wyjasnij_rozbiez": {"pl": "Wyjaśnienie rozbieżności", "uk": "Пояснення розбіжностей", "en": "Clarification of discrepancies"},
    "lacznic": {"pl": "Łącznie", "uk": "Разом", "en": "Total"},
    "przyczyny_przestojow": {"pl": "Przyczyny Przestojów", "uk": "Причини простоїв", "en": "Downtime Reasons"},
    "statystyki_pracownikow": {"pl": "Statystyki Pracowników (HR)", "uk": "Статистика працівників (HR)", "en": "Employee Statistics (HR)"},
    "nieobecni": {"pl": "Nieobecności", "uk": "Відсутності", "en": "Absences"},
    "awarie_usterki": {"pl": "Awarie / Usterki / Nieobecności", "uk": "Поломки / Несправності / Відсутності", "en": "Breakdowns / Failures / Absences"},
}

with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

before = len(translations['pl'])

for key, values in missing.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]

with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

after = len(translations['pl'])
print(f"✓ Dodano {after - before} nowych tłumaczeń")
print(f"  Razem: {after} kluczy")
