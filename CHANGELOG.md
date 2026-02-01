**# Changelog - System Biblioteka

Wszystkie istotne zmiany w projekcie będą dokumentowane w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).

## [1.1.1] - 2026-02-01 (Updated)

### 🎉 Wymiana Architektury Email

#### ❌ Stary sposób: `mailto:` protocol
- Brak możliwości załączenia raporów
- Wymaga kliknięcia "Send" w aplikacji poczty
- Nie skaluje się dla wielu odbiorców

#### ✨ Nowy sposób: Server-side SMTP + Flask-Mail

**Nowe Możliwości**:
- ✅ Automatyczne załączanie raportów (XLSX, TXT, PDF)
- ✅ Wysyłanie automatyczne (bez kliknięcia Send)
- ✅ Server-side email (bez potrzeby mail clienta na Windows)
- ✅ Konfiguracja SMTP (Gmail, Outlook, własny serwer)
- ✅ Detailne logowanie wysyłania
- ✅ Error handling i retries

### 🔧 Zmiany Techniczne

#### Frontend (`templates/dashboard_global.html`)
- ✅ Zmiana: `mailto:` protocol → `fetch() POST`
- ✅ Nowy button state: "⏳ Wysyłanie..." podczas wysyłania
- ✅ Response handling: Success/error alerts
- ✅ Async/await pattern zamiast promises
- ✅ Disabled state dla przycisku podczas wysyłania

#### Backend (`routes_api.py`)
- ✅ Nowy endpoint: `POST /api/send-report-email`
- ✅ Funkcjonalność:
  - Pobiera dane z request JSON
  - Wygeneruj/znajdź raporty w folderze `raporty/`
  - Załącz pliki (XLSX, TXT, PDF)
  - Wyślij przez SMTP
  - Zwróć JSON response
- ✅ Error handling z logami
- ✅ Autentykacja: `@login_required` + `@roles_required('lider', 'admin')`

#### Backend (`app.py`)
- ✅ Import: `from flask_mail import Mail, Message`
- ✅ Inicjalizacja: `mail = Mail(app)`
- ✅ Konfiguracja z ENV: MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD

#### Konfiguracja (`config.py`)
- ✅ MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USE_SSL
- ✅ MAIL_USERNAME, MAIL_PASSWORD
- ✅ MAIL_DEFAULT_SENDER
- ✅ Wszystkie zmienne z `.env`

#### Zmienne Środowiskowe (`.env`)
- ✅ MAIL_SERVER (default: smtp.gmail.com)
- ✅ MAIL_PORT (default: 587)
- ✅ MAIL_USE_TLS (default: True)
- ✅ MAIL_USERNAME
- ✅ MAIL_PASSWORD
- ✅ MAIL_DEFAULT_SENDER

### 📦 Nowe Zależności

```
flask-mail==0.10.0  # Wysyłanie maili przez SMTP
```

### 📚 Nowa Dokumentacja

- [SMTP_CONFIGURATION.md](SMTP_CONFIGURATION.md) - Konfiguracja SMTP (Gmail, Outlook, etc.)

---

## [1.1.0] - 2026-02-01

### ✨ Nowe Funkcjonalności

#### 📧 Wysyłanie Raportów Mailem (v1 - `mailto:` protocol)
- **Nowy przycisk**: "📧 Wyślij raport mailem" na dashboard_global
- **Konfiguracja odbiorców**: Zmienne ENV (`EMAIL_RECIPIENTS`) + fallback
- **API Endpoint**: `GET /api/email-config` zwraca listę odbiorców
- **mailto: Protocol**: Otwarcie domyślnego klienta poczty Windows
- **Formatowanie maila**: 
  - Subject: "Raport produkcyjny z dnia [DATA]"
  - Body: Wstępnie sformatowana wiadomość
  - To: Dynamiczne adresy z konfiguracji
- **CSS Styling**: Button z hover effects i animacjami

#### 📋 Dokumentacja
- `EMAIL_CONFIG.md` - Pełna dokumentacja konfiguracji
- `INSTRUKCJA_EMAIL.txt` - Instrukcja dla użytkowników
- `EMAIL_TESTING_CHECKLIST.md` - Checklist testowania

### 🔧 Zmiany Techniczne

#### Backend (`routes_api.py`)
- ✅ Nowy endpoint: `@api_bp.route('/api/email-config', methods=['GET'])`
- ✅ Wymaganie autentykacji: `@login_required`
- ✅ JSON response: `{recipients, subject_template, configured, count}`
- ✅ Error handling: graceful fallback na domyślnych odbiorców

#### Frontend (`templates/dashboard_global.html`)
- ✅ Nowy button HTML: `<button id="btnSendEmailReport">📧 Wyślij raport mailem</button>`
- ✅ JavaScript event handler: `fetch(/api/email-config)` + mailto link construction
- ✅ Funkcja: `sendEmailReport(recipients)` - konstruuje mailto URL
- ✅ Logging: `[EMAIL]` prefix w console.log dla debugowania
- ✅ Error messages: Alert dla użytkownika jeśli brakuje konfiguracji

#### Konfiguracja (`config.py`)
- ✅ Nowa zmienne: `EMAIL_RECIPIENTS` - lista odbiorców z ENV
- ✅ Parser: split(',') i strip() dla każdego emaila
- ✅ Fallback: domyślni odbiorcy jeśli ENV nie ustawiony

#### Styling (`static/css/dashboard_global.css`)
- ✅ `.btn-send-email` - główne style (kolor, padding, border)
- ✅ `.btn-send-email:hover` - hover effect z cieniem
- ✅ `.btn-send-email:active` - active state
- ✅ `.btn-end-shift-large` - sizing dla dużego przycisku

### 🐛 Fixes w tej Wersji (Wcześniejsze)

#### Report Generation (z poprzednich sesji)
- ✅ Usunięty konflikt fpdf vs fpdf2 (pip uninstall, cache purge, pip install fpdf2)
- ✅ Zainstalowane brakujące biblioteki: openpyxl, reportlab, pandas
- ✅ Fixed SQL column naming errors
- ✅ Fixed Windows Unicode encoding (emoji → ASCII)
- ✅ File migration logic (raporty_temp → raporty)
- ✅ Dual-generation strategy w `/api/pobierz-raport`

### 📦 Zależności

Nowe biblioteki wymagane (dodane wcześniej, już zainstalowane):
- `openpyxl==3.1.5` - Excel file generation
- `reportlab==4.4.9` - PDF generation
- `pandas==3.0.0` - Data analysis
- `fpdf2==2.8.5` - Better PDF library (zamiana za old fpdf)

### 🚀 Wdrażanie

#### Konfiguracja na Dev
1. `.env` zawiera: `EMAIL_RECIPIENTS=email1@example.com,email2@example.com`
2. Restart Python aplikacji
3. Test `/api/email-config` endpoint

#### Wdrażanie na QNAP
1. SSH do QNAP
2. Edytuj `.env`: `EMAIL_RECIPIENTS=rzeczywiste-adresy@firma.pl`
3. `systemctl restart raport-app`
4. Test na Windows kliencie

### 📝 Znane Problemy

- ⚠️ `mailto:` link ma limit ~2000 znaków (OK dla większości przypadków)
- ⚠️ Wymaga skonfigurowanego mail clienta na Windows
- ⚠️ Nie wysyła automatycznie (wymaga kliknięcia Send)

### ✅ Przetestowane

- ✅ Chrome + `mailto:`
- ✅ Firefox + `mailto:`
- ✅ Outlook 365 + `mailto:`
- ✅ API endpoint z autoryzacją
- ✅ Frontend button rendering i styling
- ✅ JavaScript event handling
- ✅ Configuration loading from ENV

### 📚 Dokumentacja

Nowe pliki:
- [EMAIL_CONFIG.md](EMAIL_CONFIG.md) - Tech documentation
- [INSTRUKCJA_EMAIL.txt](INSTRUKCJA_EMAIL.txt) - User guide
- [EMAIL_TESTING_CHECKLIST.md](EMAIL_TESTING_CHECKLIST.md) - QA checklist

---

## [1.0.0] - 2026-01-17

### 🎉 Wersja inicjalna systemu

#### Dodano
- **System logowania** z zarządzaniem rolami (Admin, Lider, Planista, Pracownik)
- **Dashboard produkcji** z zakładkami (Zasyp, Workowanie, Magazyn)
- **Planowanie produkcji**:
  - Dodawanie planów produkcji
  - Rozpoczynanie i kończenie zleceń
  - Śledzenie tonażu planowanego i rzeczywistego
  - Auto-carryover niezakończonych zleceń
  - Funkcja "Przejście/Zmiana"
- **Zarządzanie obsadą**:
  - Dodawanie pracowników do obsady zmianowej
  - Usuwanie pracowników z obsady
  - Kontrola dostępności pracowników
- **Dziennik zdarzeń**:
  - Zgłaszanie problemów (Awaria, Postój, Mikro zatrzymanie, Usterka)
  - Walidacja opisu (minimum 150 znaków)
  - Blokada zgłoszeń po godzinie 15:00
  - Automatyczne uzupełnianie czasu
  - Edycja zgłoszeń
  - Obliczanie czasu trwania problemu
- **Panel Lidera**:
  - Raportowanie HR (nieobecności, nadgodziny)
  - Zamykanie i zatwierdzanie zmian
  - Dodawanie uwag lidera
- **Panel Administratora**:
  - Zarządzanie pracownikami (CRUD)
  - Zarządzanie kontami użytkowników
  - Podgląd raportów HR
- **Raporty i statystyki**:
  - Export do Excel (Produkcja, Awarie, HR)
  - Raporty okresowe (miesięczne i roczne)
  - Dashboard zarządu z KPI
  - Wykresy trendów produkcji (Chart.js)
  - Analiza awarii według kategorii
- **Funkcje pomocnicze**:
  - Nawigacja po datach
  - Licznik znaków w opisach
  - Podsumowanie tonażu (plan vs wykonanie)
  - Obliczanie postępu w procentach
  - Statusy zleceń z kolorowym oznaczeniem
  - Automatyczne sortowanie zleceń (w toku → zaplanowane)

#### Bezpieczeństwo
- Sesyjne zarządzanie użytkownikami
- Kontrola dostępu oparta na rolach (RBAC)
- Parametryzowane zapytania SQL (ochrona przed SQL Injection)
- Walidacja danych wejściowych
- Tajny klucz sesji (do zmiany przez użytkownika)

#### Technologie
- **Backend**: Flask 3.0.0
- **Baza danych**: MySQL/MariaDB (utf8mb4)
- **Export**: Pandas 2.1.4 + OpenPyXL 3.1.2
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Wykresy**: Chart.js (CDN)
- **Connector**: mysql-connector-python 8.2.0

#### Dokumentacja
- README.md - Główna dokumentacja
- SZYBKI_START.md - Instrukcja szybkiego startu
- KONFIGURACJA.md - Szczegóły konfiguracji
- CHECKLIST.md - Lista kontrolna wdrożenia
- requirements.txt - Zależności Python
- .gitignore - Pliki ignorowane przez Git

#### Skrypty pomocnicze
- `setup.bat` - Automatyczna instalacja (Windows)
- `run.bat` - Uruchamianie aplikacji (Windows)
- `test_db.py` - Test połączenia z bazą danych

#### Struktura bazy danych
- **pracownicy** - Lista pracowników
- **uzytkownicy** - Konta logowania z rolami
- **dziennik_zmiany** - Zgłoszenia problemów i awarii
- **obsada_zmiany** - Obsada pracowników na zmianach
- **plan_produkcji** - Plany i realizacja produkcji
- **obecnosc** - Raportowanie HR
- **raporty_koncowe** - Zamknięte zmiany z uwagami lidera

#### Domyślne dane
- 4 domyślne konta użytkowników (admin, lider, planista, pracownik)
- 4 domyślne wpisy pracowników (Agencja 1-4)
- Automatyczne tworzenie tabel przy pierwszym uruchomieniu

#### Responsywność
- Optymalizacja dla ekranów desktopowych
- Podstawowe wsparcie dla urządzeń mobilnych
- Elastyczny layout z CSS Grid i Flexbox

---

## Planowane w przyszłych wersjach

### [1.1.0] - Planowane
- [ ] Dashboard dla roli Pracownik z uproszczonym widokiem
- [ ] Powiadomienia push dla liderów
- [ ] API REST dla integracji z innymi systemami
- [ ] Możliwość przesyłania zdjęć do zgłoszeń
- [ ] Historia zmian w planie produkcji
- [ ] Zaawansowane filtrowanie i wyszukiwanie

### [1.2.0] - Planowane
- [ ] Moduł zarządzania surowcami i magazynem
- [ ] Harmonogram przeglądów maszyn
- [ ] System ticketów dla zgłoszeń serwisowych
- [ ] Integracja z systemem kadrowym
- [ ] Automatyczne raporty email
- [ ] Multi-język (EN, DE)

### [2.0.0] - Planowane
- [ ] Przepisanie na React.js (frontend)
- [ ] API GraphQL
- [ ] Real-time updates (WebSocket)
- [ ] PWA (Progressive Web App)
- [ ] Dark mode
- [ ] Zaawansowana analityka i ML

---

## Znane problemy

### Wysokie priorytety
- Brak - system stabilny

### Średnie priorytety
- Responsywność dla małych ekranów wymaga poprawy
- Brak potwierdzenia przy dodawaniu pracownika do obsady

### Niskie priorytety
- Logo Agronetzwerk ładowane z zewnętrznego CDN
- Brak paginacji dla długich list wpisów

---

## Zgłaszanie błędów

Jeśli znajdziesz błąd, skontaktuj się z administratorem systemu lub zgłoś na:
- **Email**: ___________________
- **Telefon**: _________________

Proszę załączyć:
1. Opis błędu
2. Kroki do odtworzenia
3. Screenshoty (jeśli możliwe)
4. Wersja przeglądarki
5. Log z konsoli (jeśli dostępny)

---

**Legenda:**
- ✅ Ukończone
- 🚧 W trakcie
- ⏳ Zaplanowane
- ❌ Anulowane
- 🐛 Naprawiono błąd
- 🎨 Poprawka UI/UX
- ⚡ Poprawa wydajności
- 🔒 Bezpieczeństwo
- 📚 Dokumentacja
