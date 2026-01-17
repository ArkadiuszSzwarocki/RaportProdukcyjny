# Changelog - System Biblioteka

Wszystkie istotne zmiany w projekcie będą dokumentowane w tym pliku.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).

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
