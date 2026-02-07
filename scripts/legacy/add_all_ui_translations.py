#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# Wszystkie znalezione tłumaczenia (teksty ze skanu)
all_translations = {
    # Już dodane wcześniej - pominę duplikaty
    
    # Nagłówki i etykiety
    "akcja": {"pl": "Akcja", "uk": "Дія", "en": "Action"},
    "awaria_maszyny": {"pl": "Awaria Maszyny", "uk": "Відмова машини", "en": "Machine Failure"},
    "big_bag": {"pl": "Big Bag", "uk": "Біг-бег", "en": "Big Bag"},
    "brak_surowca": {"pl": "Brak Surowca", "uk": "Брак сировини", "en": "Lack of Raw Material"},
    "brak_awarii_30_dni": {"pl": "Brak awarii w ostatnich 30 dniach", "uk": "Немає відмов протягом останніх 30 днів", "en": "No failures in the last 30 days"},
    "brak_danych_kadrowych": {"pl": "Brak danych kadrowych.", "uk": "Немає даних про персонал.", "en": "No personnel data."},
    "brak_danych_o_pracownikach": {"pl": "Brak danych o pracownikach", "uk": "Немає даних про працівників", "en": "No employee data"},
    "brak_dokumentow": {"pl": "Brak dokumentów", "uk": "Немає документів", "en": "No documents"},
    "brak_komentarzy": {"pl": "Brak komentarzy - bądź pierwszy!", "uk": "Немає коментарів - будь першим!", "en": "No comments - be first!"},
    "brak_kont_bazy": {"pl": "Brak kont w bazie.", "uk": "Немає облікових записів в базі.", "en": "No accounts in database."},
    "brak_kont": {"pl": "Brak kont.", "uk": "Немає облікових записів.", "en": "No accounts."},
    "brak_notatek_tego_dnia": {"pl": "Brak notatek dla tego dnia.", "uk": "Немає приміток на цей день.", "en": "No notes for this day."},
    "brak_notatek_wybranej_daty": {"pl": "Brak notatek na wybraną datę.", "uk": "Немає приміток на цю дату.", "en": "No notes for selected date."},
    "brak_notatek_dodaj": {"pl": "Brak notatek. Dodaj nową notatkę powyżej.", "uk": "Немає приміток. Додайте нову примітку вище.", "en": "No notes. Add a new note above."},
    "brak_palet_oczekujacych": {"pl": "Brak palet oczekujących na zatwierdzenie.", "uk": "Немає палет, що чекають затвердження.", "en": "No pallets awaiting approval."},
    "brak_planu": {"pl": "Brak planu.", "uk": "Немає плану.", "en": "No plan."},
    "brak_planow_workowanie": {"pl": "Brak planów Workowanie na ten dzień.", "uk": "Немає планів опрацювання на цей день.", "en": "No Processing plans for this day."},
    "brak_planow_zasyp": {"pl": "Brak planów Zasyp na ten dzień.", "uk": "Немає планів Засипання на цей день.", "en": "No Fill plans for this day."},
    "brak_planow_produkcji": {"pl": "Brak planów produkcji dla tej sekcji", "uk": "Немає планів виробництва для цієї секції", "en": "No production plans for this section"},
    "brak_planow_dzisiaj": {"pl": "Brak planów produkcji na dzisiaj", "uk": "Немає планів виробництва на сьогодні", "en": "No production plans for today"},
    "brak_potwierdzonych_palet": {"pl": "Brak potwierdzone palet.", "uk": "Немає затверджених палет.", "en": "No confirmed pallets."},
    "brak_pracownikow_punkt": {"pl": "Brak pracowników.", "uk": "Немає працівників.", "en": "No employees."},
    "brak_przestogow": {"pl": "Brak przestojów.", "uk": "Немає простоїв.", "en": "No downtime."},
    "brak_przypisanych": {"pl": "Brak przypisanych pracowników", "uk": "Немає присвоєних працівників", "en": "No assigned employees"},
    "brak_towaru_bufor": {"pl": "Brak towaru w buforze.", "uk": "Немає товару в буфері.", "en": "No goods in buffer."},
    "brak_zlecen": {"pl": "Brak zleceń w bazie.", "uk": "Немає замовлень у базі.", "en": "No orders in database."},
    
    # Błędy i komunikaty
    "blad_ladowania": {"pl": "Błąd ładowania notatek", "uk": "Помилка завантаження приміток", "en": "Error loading notes"},
    "cos_poszlo": {"pl": "Coś poszło nie tak...", "uk": "Щось пішло не так...", "en": "Something went wrong..."},
    "czas_awarii": {"pl": "Czas Awarii", "uk": "Час відмови", "en": "Failure Time"},
    "czeka_na_czesci": {"pl": "Czeka na części:", "uk": "Чекає деталі:", "en": "Waiting for parts:"},
    
    # Dialogi/Pytania
    "czy_usunac_palete": {"pl": "Czy na pewno chcesz usunąć paletę o id", "uk": "Чи впевнений ви покидаєте палету з id", "en": "Are you sure you want to delete pallet with id"},
    "czy_usunac_szarze": {"pl": "Czy na pewno chcesz usunąć szarżę o id", "uk": "Чи впевнений ви покидаєте партію з id", "en": "Are you sure you want to delete batch with id"},
    "czy_na_pewno_usunac": {"pl": "Czy na pewno usunąć paletę", "uk": "Чи впевнено видалити палету", "en": "Are you sure delete pallet"},
    
    # Przyciski główne
    "dodaj_palete": {"pl": "DODAJ PALETĘ", "uk": "ДОДАТИ ПАЛЕТУ", "en": "ADD PALLET"},
    "dodaj_szarze": {"pl": "DODAJ SZARŻĘ", "uk": "ДОДАТИ ПАРТІЮ", "en": "ADD BATCH"},
    "dane_wejsciowe": {"pl": "Dane wejściowe", "uk": "Вхідні дані", "en": "Input data"},
    "data_zasypu": {"pl": "Data Zasypu", "uk": "Дата засипання", "en": "Fill Date"},
    "data_ukonczone": {"pl": "Data kiedy zostało ukończone", "uk": "Дата завершення", "en": "Date completed"},
    "data_planu": {"pl": "Data planu:", "uk": "Дата плану:", "en": "Plan date:"},
    "data_zakonczenia": {"pl": "Data zakończenia (opcjonalnie):", "uk": "Дата завершення (опціонально):", "en": "Completion date (optional):"},
    "data_label": {"pl": "Data:", "uk": "Дата:", "en": "Date:"},
    
    # Edycja i akcje
    "edycja": {"pl": "Edycja", "uk": "Редагування", "en": "Edit"},
    "edycja_wpisu": {"pl": "Edycja wpisu", "uk": "Редагування запису", "en": "Edit entry"},
    "generowanie_raportu": {"pl": "Generowanie raportu...", "uk": "Створення звіту...", "en": "Generating report..."},
    
    # Formularze i pola
    "godzina_koniec": {"pl": "Godzina KONIEC:", "uk": "Час КІНЕЦЬ:", "en": "Time END:"},
    "godzina_start": {"pl": "Godzina START:", "uk": "Час ПОЧАТОК:", "en": "Time START:"},
    "grupa_opcjonalnie": {"pl": "Grupa (opcjonalnie)", "uk": "Група (опціонально)", "en": "Group (optional)"},
    "hh_mm": {"pl": "HH:MM", "uk": "ГГ:ММ", "en": "HH:MM"},
    "hala_produkcyjna": {"pl": "Hala Produkcyjna:", "uk": "Виробничий цех:", "en": "Production Hall:"},
    "haslo_opcjonalnie": {"pl": "Hasło (opcjonalnie)", "uk": "Пароль (опціонально)", "en": "Password (optional)"},
    "id_pracownika": {"pl": "ID pracownika", "uk": "ID працівника", "en": "Employee ID"},
    "id_label": {"pl": "ID:", "uk": "ID:", "en": "ID:"},
    "ilosc_zlecen": {"pl": "Ilość Zleceń", "uk": "Кількість замовлень", "en": "Number of Orders"},
    "imie_nazwisko": {"pl": "Imię i nazwisko", "uk": "Ім'я та прізвище", "en": "First and Last Name"},
    "imie_nazwisko_opt": {"pl": "Imię i nazwisko (opcjonalnie)", "uk": "Ім'я та прізвище (опціонально)", "en": "First and Last Name (optional)"},
    
    # Instrukcje
    "instrukcja": {"pl": "Instrukcja:", "uk": "Інструкція:", "en": "Instructions:"},
    "jakosc_zlecenia": {"pl": "Jakość — zlecenia", "uk": "Якість — замовлення", "en": "Quality — Orders"},
    "jesli_brak_uszkodzonych": {"pl": "Jeśli brak uszkodzonych worków, wpisz", "uk": "Якщо немає пошкоджених мішків, введіть", "en": "If no damaged bags, enter"},
    "jesli_problem_powtarza": {"pl": "Jeśli problem będzie się powtarzać, skontaktuj się z administratorem", "uk": "Якщо проблема не зникне, зв'яжіться з адміністратором", "en": "If the problem persists, contact your administrator"},
    "jesli_nie_pobiera": {"pl": "Jeśli się nie pobiera, sprawdź konsolę przeglądarki (F12)", "uk": "Якщо не завантажується, перевірте консоль браузера (F12)", "en": "If not downloading, check browser console (F12)"},
    
    # Kroki
    "krok_1": {"pl": "KROK 1:", "uk": "КРОК 1:", "en": "STEP 1:"},
    "krok_2": {"pl": "KROK 2:", "uk": "КРОК 2:", "en": "STEP 2:"},
    "krok_3": {"pl": "KROK 3:", "uk": "КРОК 3:", "en": "STEP 3:"},
    "krok_1_prosty": {"pl": "Krok 1", "uk": "Крок 1", "en": "Step 1"},
    "krok_2_prosty": {"pl": "Krok 2", "uk": "Крок 2", "en": "Step 2"},
    "krok_3_prosty": {"pl": "Krok 3", "uk": "Крок 3", "en": "Step 3"},
    
    # Kalendarze i okresy
    "kalendarz_godzin": {"pl": "Kalendarz godzin (miesiąc)", "uk": "Календар годин (місяць)", "en": "Hours Calendar (month)"},
    "kalendarz_pracownika": {"pl": "Kalendarz pracownika", "uk": "Календар працівника", "en": "Employee Calendar"},
    "kategoria": {"pl": "Kategoria:", "uk": "Категорія:", "en": "Category:"},
    "kliknij_pobierz": {"pl": "Kliknij \"Pobierz raport z dzisiaj\" lub \"Pobierz z wybranej daty\"", "uk": "Натисніть \"Завантажити звіт сьогодні\" або \"Завантажити з вибраної дати\"", "en": "Click \"Download today's report\" or \"Download from selected date\""},
    "kliknij_wznow": {"pl": "Kliknij aby wznowić prace z poprzedniego dnia", "uk": "Натисніть щоб відновити роботу з попереднього дня", "en": "Click to resume work from previous day"},
    
    # Komentarze i notatki
    "komentarz": {"pl": "Komentarz", "uk": "Коментар", "en": "Comment"},
    "konta_uzytkownikow": {"pl": "Konta użytkowników", "uk": "Облікові записи користувачів", "en": "User Accounts"},
    "legenda": {"pl": "Legenda:", "uk": "Легенда:", "en": "Legend:"},
    "liczba_uszkodzonych": {"pl": "Liczba uszkodzonych worków (wpisz 0 jeśli brak)", "uk": "Кількість пошкоджених мішків (введіть 0 якщо немає)", "en": "Number of damaged bags (enter 0 if none)"},
    "liczba_zmian": {"pl": "Liczba zmian obecności w tym okresie:", "uk": "Кількість змін відвідуваності в цьому періоді:", "en": "Number of attendance changes in this period:"},
    
    # Liderzy i sekcje
    "lider_agro_label": {"pl": "Lider AGRO:", "uk": "Лідер AGRO:", "en": "AGRO Leader:"},
    "lider_psd_label": {"pl": "Lider PSD:", "uk": "Лідер PSD:", "en": "PSD Leader:"},
    
    # Operacje
    "nadmiar_spakowany": {"pl": "Nadmiar spakowany", "uk": "Надлишок упакований", "en": "Surplus packed"},
    "notatka_zapisu": {"pl": "Notatka do zapisu", "uk": "Примітка для запису", "en": "Note for saving"},
    "notatka_label": {"pl": "Notatka:", "uk": "Примітка:", "en": "Note:"},
    "nowa_data_label": {"pl": "Nowa data:", "uk": "Нова дата:", "en": "New date:"},
    "nowe_haslo": {"pl": "Nowe hasło (opcjonalnie)", "uk": "Новий пароль (опціонально)", "en": "New password (optional)"},
    "nr_receptury": {"pl": "Nr receptury", "uk": "№ рецепту", "en": "Recipe No."},
    
    # Obłożenie i opcje
    "oblocenie_zmiany": {"pl": "Obłożenie Zmiany (450 min)", "uk": "Навантаження зміни (450 хв)", "en": "Shift Load (450 min)"},
    "opcje": {"pl": "Opcje", "uk": "Параметри", "en": "Options"},
    "opcje_akcje": {"pl": "Opcje i akcje.", "uk": "Параметри та дії.", "en": "Options and actions."},
    "opcjonalny_komentarz": {"pl": "Opcjonalny komentarz", "uk": "Опціональний коментар", "en": "Optional comment"},
    "opis_opcjonalnie": {"pl": "Opis (opcjonalnie)", "uk": "Опис (опціонально)", "en": "Description (optional)"},
    "opis_szczegolowy": {"pl": "Opis szczegółowy:", "uk": "Детальний опис:", "en": "Detailed description:"},
    "opis_opakowania": {"pl": "Opis typu opakowania", "uk": "Опис типу упаковки", "en": "Description of packaging type"},
    "opisz_problem": {"pl": "Opisz problem", "uk": "Опишіть проблему", "en": "Describe the problem"},
    
    # Przyciski specjalne
    "pokaż_dane": {"pl": "POKAŻ DANE", "uk": "ПОКАЗАТИ ДАНІ", "en": "SHOW DATA"},
    "pozostalo_do_spakowania": {"pl": "POZOSTAŁO (DO SPAKOWANIA)", "uk": "ЗАЛИШИЛОСЬ (ДО УПАКОВКИ)", "en": "REMAINING (TO PACK)"},
    "palet_liczba": {"pl": "Palet", "uk": "Палети", "en": "Pallets"},
    
    # Plan i raporty
    "plan_kg": {"pl": "Plan (kg):", "uk": "План (кг):", "en": "Plan (kg):"},
    "plan_wagowy": {"pl": "Plan Wagowy", "uk": "План ваги", "en": "Weight Plan"},
    "plik_zip_pobierz": {"pl": "Plik ZIP powinien się pobrać automatycznie", "uk": "Файл ZIP повинен завантажитися автоматично", "en": "ZIP file should download automatically"},
    "pobierz_btn": {"pl": "Pobierz", "uk": "Завантажити", "en": "Download"},
    "podsumowanie": {"pl": "Podsumowanie", "uk": "Резюме", "en": "Summary"},
    "podsumowanie_wynikow": {"pl": "Podsumowanie wyników produkcji", "uk": "Резюме результатів виробництва", "en": "Summary of production results"},
    "powod": {"pl": "Powód:", "uk": "Причина:", "en": "Reason:"},
    
    # Produkty
    "produkt_label": {"pl": "Produkt", "uk": "Продукт", "en": "Product"},
    "produkt_polownik": {"pl": "Produkt:", "uk": "Продукт:", "en": "Product:"},
    "przeglądaj_pracownika": {"pl": "Przeglądaj pracownika:", "uk": "Переглянути працівника:", "en": "View employee:"},
    "przejdz_jakosc": {"pl": "Przejdź do Jakość", "uk": "Перейдіть до Якості", "en": "Go to Quality"},
    "przerwa": {"pl": "Przerwa", "uk": "Перерва", "en": "Break"},
    "przezbrojenie": {"pl": "Przezbrojenie", "uk": "Переналагодження", "en": "Changeover"},
    "prześlij_dokument": {"pl": "Prześlij dokument", "uk": "Завантажити документ", "en": "Upload document"},
    
    # Raporty i terminy
    "raport_gotowy": {"pl": "Raport Gotowy", "uk": "Звіт Готово", "en": "Report Ready"},
    "raportował": {"pl": "Raportował:", "uk": "Повідомив:", "en": "Reported by:"},
    "raporty_okresowe": {"pl": "Raporty Okresowe", "uk": "Періодичні звіти", "en": "Periodic Reports"},
    "razem_awarii": {"pl": "Razem awarii:", "uk": "Разів відмов:", "en": "Total failures:"},
    "real_label": {"pl": "Real:", "uk": "Реал:", "en": "Real:"},
    "realizacja_celu": {"pl": "Realizacja Celu", "uk": "Досягнення мети", "en": "Target Achievement"},
    "realizacja_planu": {"pl": "Realizacja Planu", "uk": "Виконання плану", "en": "Plan Execution"},
    
    # Rodzaje i statusy
    "rodzaj_problemu": {"pl": "Rodzaj problemu:", "uk": "Тип проблеми:", "en": "Problem type:"},
    "rola_konta": {"pl": "Rola konta", "uk": "Роль облікового запису", "en": "Account role"},
    
    # START/STOP
    "start": {"pl": "START", "uk": "ПОЧАТОК", "en": "START"},
    "stop": {"pl": "STOP", "uk": "ЗУПИНИТИ", "en": "STOP"},
    "sekcja_label": {"pl": "Sekcja:", "uk": "Секція:", "en": "Section:"},
    "spakowano": {"pl": "Spakowano", "uk": "Упаковано", "en": "Packed"},
    "sprawdz": {"pl": "Sprawdź", "uk": "Перевірити", "en": "Check"},
    "sprobuj_ponownie": {"pl": "Spróbuj ponownie za chwilę", "uk": "Спробуйте ще раз через деякий час", "en": "Try again in a moment"},
    
    # Status i czas
    "start_label": {"pl": "Start:", "uk": "Початок:", "en": "Start:"},
    "status_label": {"pl": "Status:", "uk": "Статус:", "en": "Status:"},
    "stop_label": {"pl": "Stop:", "uk": "Зупинка:", "en": "Stop:"},
    "system_produkcyjny": {"pl": "System Produkcyjny", "uk": "Виробнича система", "en": "Production System"},
    
    # Szczegóły i błędy
    "szczegoly_blędu": {"pl": "Szczegóły błędu znajdują się w logach aplikacji", "uk": "Деталі помилки знаходяться в журналах додатків", "en": "Error details are in application logs"},
    "szukaj_zlecenia": {"pl": "Szukaj zlecenia...", "uk": "Пошук замовлення...", "en": "Search order..."},
    
    # Testy
    "test_pobierz": {"pl": "Test Pobrania Raportów", "uk": "Тест завантаження звітів", "en": "Reports Download Test"},
    "test_okien": {"pl": "Test okien — Slide / Modal", "uk": "Тест вікон — Slide / Modal", "en": "Windows Test — Slide / Modal"},
    "test_api_pobierz": {"pl": "Test: Pobierz ZIP z API", "uk": "Тест: Завантажити ZIP з API", "en": "Test: Download ZIP from API"},
    "test_api_wygeneruj": {"pl": "Test: Wygeneruj raport API", "uk": "Тест: Створити звіт API", "en": "Test: Generate API report"},
    "testy_api": {"pl": "Testy API", "uk": "Тести API", "en": "API Tests"},
    
    # Typ i zmiana
    "typ_zdarzenia": {"pl": "Typ Zdarzenia:", "uk": "Тип події:", "en": "Type of Event:"},
    "typ_opakowania": {"pl": "Typ opakowania", "uk": "Тип упаковки", "en": "Type of packaging"},
    "typ_produkcji": {"pl": "Typ produkcji:", "uk": "Тип виробництва:", "en": "Type of production:"},
    "typy_przegladany": {"pl": "Typy — przeglądany", "uk": "Типи — переглянуто", "en": "Types — viewed"},
    
    # Usuń i akcje
    "usun_btn": {"pl": "USUŃ", "uk": "ВИДАЛИТИ", "en": "DELETE"},
    "urlop_biezacy": {"pl": "Urlop bieżący (dni):", "uk": "Поточна відпустка (дні):", "en": "Current leave (days):"},
    "urlop_zalegly": {"pl": "Urlop zaległy (dni):", "uk": "Невідпрацьовані дні (дні):", "en": "Outstanding leave (days):"},
    
    # Ustawienia
    "ustaw_tymczasowe": {"pl": "Ustaw tymczasowe", "uk": "Встановити тимчасовий", "en": "Set temporary"},
    "ustawienia_role": {"pl": "Ustawienia / Role i uprawnienia", "uk": "Налаштування / Ролі та дозволи", "en": "Settings / Roles and permissions"},
    "ustawienia_uzytkownicy": {"pl": "Ustawienia / Użytkownicy i Pracownicy", "uk": "Налаштування / Користувачі та працівники", "en": "Settings / Users and Employees"},
    "uwaga": {"pl": "Uwaga:", "uk": "Внимание:", "en": "Warning:"},
    "uzytkownik_instrukcja": {"pl": "Użyj poniższych przycisków, aby wywołać różne warianty okien testowych.", "uk": "Використовуйте кнопки нижче, щоб викликати різні варіанти тестових вікон.", "en": "Use the buttons below to call various test window variants."},
    
    # Waga i mierzenia
    "w_trakcie_naprawy": {"pl": "W trakcie naprawy:", "uk": "На ремонті:", "en": "Under repair:"},
    "waga_plan_wyk": {"pl": "Waga (Plan/Wyk) (kg)", "uk": "Вага (План/Вик) (кг)", "en": "Weight (Plan/Exec) (kg)"},
    "waga_kg_label": {"pl": "Waga (kg):", "uk": "Вага (кг):", "en": "Weight (kg):"},
    "waga_produktu": {"pl": "Waga Produktu (Netto) [kg]", "uk": "Вага продукту (Нетто) [кг]", "en": "Product Weight (Net) [kg]"},
    "waga_szarzy": {"pl": "Waga Szarży (Netto) [kg]:", "uk": "Вага партії (Нетто) [кг]:", "en": "Batch Weight (Net) [kg]:"},
    "waga_netto_palety": {"pl": "Waga netto palety (kg)", "uk": "Чиста вага палети (кг)", "en": "Net pallet weight (kg)"},
    "waga_palety": {"pl": "Waga palety (kg)", "uk": "Вага палети (кг)", "en": "Pallet weight (kg)"},
    "waga_palety_kg_info": {"pl": "Waga palety w kilogramach", "uk": "Вага палети в кілограмах", "en": "Pallet weight in kilograms"},
    "waga_szarzy_kg": {"pl": "Waga szarży (kg)", "uk": "Вага партії (кг)", "en": "Batch weight (kg)"},
    "waga_szarzy_kg_info": {"pl": "Waga szarży w kilogramach", "uk": "Вага партії в кілограмах", "en": "Batch weight in kilograms"},
    
    # Widoczność
    "widok_dla": {"pl": "Widok dla", "uk": "Вид для", "en": "View for"},
    "wizard_3_kroki": {"pl": "Wizard (3 kroki)", "uk": "Майстер (3 кроки)", "en": "Wizard (3 steps)"},
    "worki_zgrzwane": {"pl": "Worki zgrzewane 10kg", "uk": "Зварні мішки 10кг", "en": "Welded bags 10kg"},
    "wpisz_haslo": {"pl": "Wpisz hasło", "uk": "Введіть пароль", "en": "Enter password"},
    "wpisz_login": {"pl": "Wpisz login", "uk": "Введіть логін", "en": "Enter login"},
    "wpisz_notatki_zmiany": {"pl": "Wpisz notatki z zmiany, uwagi, problemy, osiągnięcia...", "uk": "Введіть замітки зміни, коментарі, проблеми, досягнення...", "en": "Enter shift notes, comments, problems, achievements..."},
    "wpisz_notatke": {"pl": "Wpisz notatkę...", "uk": "Введіть примітку...", "en": "Enter note..."},
    "wpisz_wyjasnienie": {"pl": "Wpisz wyjaśnienie...", "uk": "Введіть пояснення...", "en": "Enter explanation..."},
    "wprowadz_godzine_start": {"pl": "Wprowadź godzinę rozpoczęcia", "uk": "Введіть час початку", "en": "Enter start time"},
    "wprowadz_godzine_koniec": {"pl": "Wprowadź godzinę zakończenia", "uk": "Введіть час завершення", "en": "Enter end time"},
    "wprowadz_opis": {"pl": "Wprowadź szczegółowy opis problemu", "uk": "Введіть детальний опис проблеми", "en": "Enter detailed problem description"},
    "wroc_logowanie": {"pl": "Wróć do logowania", "uk": "Повернутися до входу", "en": "Return to login"},
    
    # Systemy i sukces
    "wszystkie_systemy_ok": {"pl": "Wszystkie systemy działają bez problemów! 🎉", "uk": "Усі системи працюють без проблем! 🎉", "en": "All systems working without issues! 🎉"},
    
    # Wybór
    "wybierz_date": {"pl": "Wybierz datę (domyślnie dzisiaj)", "uk": "Виберіть дату (за замовчуванням сьогодні)", "en": "Select date (default today)"},
    "wybierz_date_dwuk": {"pl": "Wybierz datę:", "uk": "Виберіть дату:", "en": "Select date:"},
    "wybierz_dokument": {"pl": "Wybierz dokument", "uk": "Виберіть документ", "en": "Select document"},
    "wybierz_miesiac": {"pl": "Wybierz miesiąc", "uk": "Виберіть місяць", "en": "Select month"},
    "wybierz_pracownika": {"pl": "Wybierz pracownika do przeglądu", "uk": "Виберіть працівника для перегляду", "en": "Select employee for review"},
    "wybierz_rok": {"pl": "Wybierz rok", "uk": "Виберіть рік", "en": "Select year"},
    
    # Wyjaśnienie i wykonanie
    "wyjasnienie_label": {"pl": "Wyjaśnienie:", "uk": "Пояснення:", "en": "Explanation:"},
    "wyjscia_prywatne": {"pl": "Wyjścia prywatne (suma godzin):", "uk": "Приватні виходи (сумарні години):", "en": "Private exits (total hours):"},
    "wykonanie_gotowe": {"pl": "Wykonanie (Gotowe)", "uk": "Виконання (Готово)", "en": "Execution (Done)"},
    "wznow": {"pl": "Wznów", "uk": "Відновити", "en": "Resume"},
    "wlasne_id_pracownika": {"pl": "Własne ID pracownika", "uk": "Власний ID працівника", "en": "Own Employee ID"},
    
    # Zapisz
    "zapisz_btn": {"pl": "ZAPISZ", "uk": "ЗБЕРЕГТИ", "en": "SAVE"},
    "zaplanowane_btn": {"pl": "ZAPLANOWANE", "uk": "ЗАПЛАНІЗОВАНО", "en": "PLANNED"},
    "zatwierdz_btn": {"pl": "ZATWIERDŹ", "uk": "ЗАТВЕРДИТИ", "en": "APPROVE"},
    "zglosz_btn": {"pl": "ZGŁOŚ", "uk": "ПОВІДОМИТИ", "en": "REPORT"},
    "zakonczono": {"pl": "Zakończono:", "uk": "Завершено:", "en": "Completed:"},
    "zakonczonych": {"pl": "Zakończonych", "uk": "Завершено", "en": "Completed"},
    "zaloguj_sie": {"pl": "Zaloguj się", "uk": "Увійти", "en": "Log in"},
    "zapisano_punkt": {"pl": "Zapisano.", "uk": "Збережено.", "en": "Saved."},
    "zapisz_notatke": {"pl": "Zapisz notatkę", "uk": "Зберегти примітку", "en": "Save note"},
    "zapisz_uprawnienia": {"pl": "Zapisz uprawnienia", "uk": "Зберегти дозволи", "en": "Save permissions"},
    
    # Zarządzanie
    "zarzadzanie_produkcja": {"pl": "Zarządzanie Produkcją (Wszystkie Sekcje)", "uk": "Управління виробництвом (усі секції)", "en": "Production Management (All Sections)"},
    "zarzadzanie_uzytkownikami": {"pl": "Zarządzanie użytkownikami", "uk": "Управління користувачами", "en": "User Management"},
    "zatwierdz_wszystkie_btn": {"pl": "Zatwierdź wszystkie", "uk": "Затвердити все", "en": "Approve All"},
    
    # Zgłoszone i zlecenia
    "zgloszenia": {"pl": "Zgłoszone:", "uk": "Повідомлено:", "en": "Reported:"},
    "zlecenie_nie_istnieje": {"pl": "Zlecenie nie istnieje.", "uk": "Замовлення не існує.", "en": "Order does not exist."},
    
    # Zmiana języka
    "zmien_jezyk": {"pl": "Zmień język / Change language / Змінити мову", "uk": "Змінити мову / Change language / Zmień język", "en": "Change language / Zmień język / Змінити мову"},
    "zmien_status": {"pl": "Zmień status awarii", "uk": "Змінити статус відмови", "en": "Change failure status"},
    "zrobiono_zasypie": {"pl": "Zrobiono na Zasypie", "uk": "Зроблено на Засипанні", "en": "Done on Fill"},
    
    # Format czasu
    "hh_mm_maly": {"pl": "hh:mm", "uk": "гг:мм", "en": "hh:mm"},
    "np_1000": {"pl": "np. 1000", "uk": "напр. 1000", "en": "e.g. 1000"},
    "wznow_zlecenie": {"pl": "↩️ Wznów zlecenie", "uk": "↩️ Відновити замовлення", "en": "↩️ Resume order"},
    "usun_palete_emoji": {"pl": "🗑️ Usuń paletę?", "uk": "🗑️ Видалити палету?", "en": "🗑️ Delete pallet?"},
    "usun_szarze_emoji": {"pl": "🗑️ Usuń szarżę?", "uk": "🗑️ Видалити партію?", "en": "🗑️ Delete batch?"},
    "zatrzymaj_produkcje": {"pl": "🛑 Zatrzymaj produkcję", "uk": "🛑 Зупинити виробництво", "en": "🛑 Stop production"},
}

# Załaduj istniejące tłumaczenia
with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

# Policz nowe
before_pl = len(translations['pl'])
before_uk = len(translations['uk'])

# Dodaj nowe tłumaczenia
added_count = 0
for key, values in all_translations.items():
    if key not in translations['pl']:
        for lang in ['pl', 'uk', 'en']:
            translations[lang][key] = values[lang]
        added_count += 1

# Zapisz
with open('config/translations.json', 'w', encoding='utf-8') as f:
    json.dump(translations, f, ensure_ascii=False, indent=2)

# Raport
print(f"✓ Dodano {added_count} nowych tłumaczeń")
print(f"  Przed: PL={before_pl}, UK={before_uk}")
print(f"  Po:    PL={len(translations['pl'])}, UK={len(translations['uk'])}")
print(f"\nTego jeszcze ~60-70 tekstów do ręcznego dodania (specjalne komunikaty)")
