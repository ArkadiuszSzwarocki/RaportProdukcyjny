# 📋 Checklist Wdrożenia Systemu Biblioteka

## ✅ Przed uruchomieniem

### 1. Wymagania systemowe
- [ ] Python 3.8 lub nowszy zainstalowany
- [ ] MySQL/MariaDB Server uruchomiony
- [ ] Dostęp do serwera MySQL (host, port, user, password)
- [ ] Co najmniej 100 MB wolnego miejsca na dysku

### 2. Instalacja Python
- [ ] Python dodany do PATH
- [ ] pip zainstalowany i zaktualizowany (`python -m pip install --upgrade pip`)

### 3. Konfiguracja bazy danych
- [ ] Baza danych `biblioteka` utworzona
- [ ] Użytkownik `biblioteka` utworzony
- [ ] Uprawnienia nadane użytkownikowi
- [ ] Kodowanie ustawione na utf8mb4

## 🔧 Instalacja

### 4. Konfiguracja projektu
- [ ] Repozytorium sklonowane / pliki pobrane
- [ ] Plik `requirements.txt` obecny
- [ ] `setup.bat` uruchomiony (lub ręczna instalacja zależności)
- [ ] Wirtualne środowisko `.venv` utworzone
- [ ] Wszystkie pakiety zainstalowane

### 5. Konfiguracja aplikacji
- [ ] Plik `app.py` otwarty do edycji
- [ ] Parametry `db_config` (linie 11-18) zaktualizowane:
  - [ ] host
  - [ ] port
  - [ ] database
  - [ ] user
  - [ ] password
- [ ] `app.secret_key` (linia 8) zmieniony na losowy ciąg

### 6. Test połączenia
- [ ] `test_db.py` uruchomiony
- [ ] Połączenie z bazą danych działa
- [ ] Tabele widoczne w bazie (po pierwszym uruchomieniu)

## 🚀 Pierwsze uruchomienie

### 7. Start aplikacji
- [ ] `python app.py` lub `run.bat` uruchomiony
- [ ] Brak błędów w konsoli
- [ ] Tabele automatycznie utworzone
- [ ] Domyślni użytkownicy dodani
- [ ] Agencje 1-4 dodane do pracowników

### 8. Test logowania
- [ ] http://localhost:5000 otwarte w przeglądarce
- [ ] Logowanie jako `admin` / `masterkey` działa
- [ ] Dashboard produkcji wyświetla się poprawnie
- [ ] Panel admina dostępny
- [ ] Wylogowanie działa

## 🔒 Bezpieczeństwo

### 9. Zmiana domyślnych haseł
- [ ] Hasło dla `admin` zmienione
- [ ] Hasło dla `lider` zmienione
- [ ] Hasło dla `planista` zmienione
- [ ] Hasło dla `pracownik` zmienione

### 10. Zabezpieczenia dodatkowe
- [ ] `app.secret_key` zmieniony (ponowne sprawdzenie!)
- [ ] Hasło do bazy danych jest silne
- [ ] Port 5000 zabezpieczony firewallem (tylko lokalna sieć)
- [ ] Backup bazy danych skonfigurowany

## 📊 Konfiguracja danych

### 11. Dodanie pracowników
- [ ] Panel admina otwarty
- [ ] Prawdziwi pracownicy dodani (zamiast Agencja 1-4)
- [ ] Imiona i nazwiska poprawne

### 12. Dodanie użytkowników
- [ ] Konta dla rzeczywistych liderów utworzone
- [ ] Konta dla planistów utworzone
- [ ] Testowe konta usunięte lub hasła zmienione

### 13. Test podstawowych funkcji
- [ ] Dodanie planu produkcji działa
- [ ] Start/koniec zlecenia działa
- [ ] Dodanie pracownika do obsady działa
- [ ] Zgłoszenie problemu działa
- [ ] Edycja wpisu działa
- [ ] Eksport do Excel działa
- [ ] Raporty okresowe wyświetlają się

## 🏭 Środowisko produkcyjne

### 14. Optymalizacja
- [ ] `debug=False` w `app.py`
- [ ] WSGI server zainstalowany (Gunicorn/Waitress)
- [ ] Reverse proxy skonfigurowany (Nginx/Apache)
- [ ] HTTPS włączone (certyfikat SSL)
- [ ] Logowanie do pliku włączone

### 15. Monitorowanie
- [ ] Automatyczny restart aplikacji skonfigurowany
- [ ] Logi aplikacji regularnie sprawdzane
- [ ] Backup bazy danych automatyczny
- [ ] Monitoring dostępności serwera

### 16. Dokumentacja
- [ ] README.md przeczytany przez zespół
- [ ] SZYBKI_START.md udostępniony użytkownikom
- [ ] KONFIGURACJA.md zachowany dla IT
- [ ] Dane kontaktowe do wsparcia technicznego podane

## 📚 Szkolenie użytkowników

### 17. Szkolenie dla Administratorów
- [ ] Zarządzanie pracownikami
- [ ] Zarządzanie kontami użytkowników
- [ ] Backup i przywracanie bazy

### 18. Szkolenie dla Liderów
- [ ] Rozpoczynanie/kończenie zleceń
- [ ] Zarządzanie obsadą
- [ ] Zgłaszanie problemów
- [ ] Raportowanie HR
- [ ] Zamykanie zmian

### 19. Szkolenie dla Planistów
- [ ] Dodawanie planów produkcji
- [ ] Edycja tonażu
- [ ] Eksport raportów
- [ ] Przegląd statystyk

### 20. Szkolenie dla Pracowników
- [ ] Podstawowa nawigacja
- [ ] Zgłaszanie problemów
- [ ] Edycja własnych zgłoszeń

## ✅ Go-Live Checklist

### 21. Dzień startu
- [ ] Wszystkie powyższe punkty wykonane
- [ ] Zespół poinformowany o starcie
- [ ] Helpdesk/wsparcie gotowe
- [ ] Plan wycofania przygotowany (na wypadek problemów)
- [ ] Pierwszy dzień produkcyjny zaplanowany
- [ ] Komunikat do pracowników wysłany

### 22. Po starcie (pierwszy tydzień)
- [ ] Codzienne sprawdzanie logów
- [ ] Feedback od użytkowników zbierany
- [ ] Drobne problemy naprawiane
- [ ] Performance monitorowany
- [ ] Backup weryfikowany

### 23. Po miesiącu
- [ ] Przegląd wykorzystania systemu
- [ ] Optymalizacja na podstawie danych
- [ ] Aktualizacja dokumentacji (jeśli potrzebna)
- [ ] Planowanie nowych funkcji

---

## 🆘 Kontakty wsparcia

**IT Support:**
- Email: _____________________
- Telefon: ___________________
- Dostępność: ________________

**Administrator Systemu:**
- Imię i nazwisko: ___________
- Email: _____________________
- Telefon: ___________________

**Vendor (w razie poważnych problemów):**
- Firma: ____________________
- Email: _____________________
- Telefon: ___________________

---

**Data wdrożenia:** ______________  
**Osoba odpowiedzialna:** ______________  
**Status:** ☐ W trakcie ☐ Ukończone ☐ Uruchomione
