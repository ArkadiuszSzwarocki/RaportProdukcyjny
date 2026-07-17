# Biblioteka - System Zarządzania Produkcją Agronetzwerk

System webowy do zarządzania produkcją i planowaniem oraz do raportowania
zdarzeń w zakładzie produkcyjnym.

## 📋 Funkcjonalności

### Dla Wszystkich Użytkowników

- ✅ Logowanie z różnymi poziomami uprawnień (Admin, Lider, Planista, Pracownik)
- 📊 Podgląd planu produkcji z podziałem na sekcje (Zasyp, Workowanie, Magazyn)
- 📅 Nawigacja po datach — przeglądanie historii i planowanie przyszłych zdarzeń
- 🚨 Zgłaszanie problemów produkcyjnych (awarie, postoje, mikro-zatrzymania, usterki)
- 👷 Zarządzanie obsadą zmianową

### Dla Planisty

- 📝 Dodawanie planów produkcji
- ✏️ Edycja tonażu planowanego i rzeczywistego
- 📈 Eksport raportów do Excel
- 📊 Dostęp do raportów okresowych

### Dla Lidera

- 👑 Wszystkie uprawnienia Planisty
- ▶️ Rozpoczynanie i kończenie zleceń produkcyjnych
- 🔄 Zarządzanie przejściami/zmianami
- 📋 Raportowanie HR (nieobecności, nadgodziny)
- ✔️ Zamykanie i zatwierdzanie zmian
- 🗑️ Usuwanie wpisów

### Dla Admina

- ⚙️ Panel administracyjny
- 👥 Zarządzanie pracownikami (dodawanie, edycja, usuwanie)
- 🔐 Zarządzanie kontami użytkowników
- 📊 Pełny dostęp do wszystkich funkcji

## 🛠️ Technologie

- **Backend**: Flask 3.0.0 (Python)
- **Baza danych**: MySQL/MariaDB
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Wykresy**: Chart.js
- **Export**: Pandas + OpenPyXL (Excel)

## 📦 Instalacja

### Wymagania

- Python 3.8+
- MySQL/MariaDB Server
- pip (menedżer pakietów Python)

### Kroki instalacji

1. **Sklonuj repozytorium** (lub pobierz pliki)

```bash
cd C:\path\to\RaportProdukcyjny
```

1. **Utwórz wirtualne środowisko**

```bash
python -m venv .venv
.venv\Scripts\activate
```

1. **Zainstaluj zależności**

```bash
pip install -r requirements.txt
```

#### Zależności developerskie

Jeśli chcesz uruchamiać testy lokalnie lub w środowisku CI,
zainstaluj zależności developerskie:

```bash
pip install -r requirements-dev.txt
```

1. **Skonfiguruj bazę danych**

Edytuj plik `app.py` i dostosuj konfigurację bazy danych (linie 11-18):

```python
db_config = {
    'host': '192.168.0.18',  # Adres serwera MySQL
    'port': 3307,            # Port (domyślnie 3307)
    'database': 'biblioteka',# Nazwa bazy
    'user': 'biblioteka',    # Użytkownik
    'password': 88888888888888,  # Hasło
    'charset': 'utf8mb4'
}
```

1. **Uruchom aplikację**

```bash
python app.py
```

Aplikacja będzie dostępna pod adresem: `http://localhost:5000`

## 🗄️ Struktura Bazy Danych

System automatycznie tworzy następujące tabele:

- **pracownicy** — lista pracowników
- **uzytkownicy** — konta logowania
- **dziennik_zmiany** — zgłoszenia problemów/awarii
- **obsada_zmiany** — obsada pracowników na zmianach
- **plan_produkcji** — plany i realizacja produkcji
- **obecnosc** — raportowanie HR (nieobecności/nadgodziny)
- **raporty_koncowe** — zamknięte zmiany z uwagami lidera

## 📊 Moduły Systemu

### 1. Dashboard Produkcji (`/`)

- Podgląd planu produkcji na wybrany dzień
- Śledzenie status zleceń (zaplanowane → w toku → zakończone)
- Zgłaszanie problemów produkcyjnych
- Zarządzanie obsadą zmianową

### 2. Panel Admina (`/admin`)

- Zarządzanie pracownikami
- Zarządzanie kontami użytkowników
- Raportowanie HR

### 3. Raporty Okresowe (`/raporty_okresowe`)

- Statystyki miesięczne i roczne
- Wykresy trendów produkcji
- Analiza awarii według kategorii

### 4. Dashboard Zarządu (`/zarzad`)

- KPI produkcyjne (zlecenia, tony, czas pracy)
- Analiza awarii i przestojów
- Statystyki pracowników

### 5. Export Excel (`/export_excel`)

- Raport dzienny zawierający:
    - Arkusz "Produkcja" — plan i wykonanie
    - Arkusz "Awarie" — problemy produkcyjne
    - Arkusz "HR" — nieobecności i nadgodziny

## 🏗️ Architektura i Serwisy

### Service-Oriented Architecture

Projekt wykorzystuje service-oriented architecture do organizacji logiki biznesowej.
Serwisy enkapsulują złożone operacje biznesowe i ułatwiają testowanie oraz ponowne użycie kodu.

#### **DashboardService** (`app/services/dashboard_service.py`)

Odpowiada za agregację danych wyświetlanych na pulpicie głównym.

**Główne metody:**
- `get_basic_staff_data()` — dane dotyczące przypisania pracowników
- `get_journal_entries()` — wpisy dziennika ze formatowaniem czasów
- `get_warehouse_data()` — dane magazynu (palety, niezatwierdzenia)
- `get_production_plans()` — plany produkcji z sumami
- `get_hr_and_leave_data()` — dane HR (urlopy, nieobecności)
- `get_quality_and_leave_requests()` — liczba raportów jakości i wnioski
- `get_shift_notes()` — notatki zmian liderów
- `get_full_plans_for_sections()` — pełne plany dla sekcji (Zasyp, Workowanie, Magazyn)

**Przykład użycia:**
```python
from app.services.dashboard_service import DashboardService

staff = DashboardService.get_basic_staff_data()
plans = DashboardService.get_production_plans()
warehouse = DashboardService.get_warehouse_data()
```

**Testowanie:** 15 jednostkowych testów w `tests/test_dashboard_service.py`

#### **ReportGenerationService** (`app/services/report_generation_service.py`)

Orchestruje workflow zamykania zmian i generowania raportów.

**Główne metody:**
- `close_shift_and_generate_reports(uwagi_lidera)` → Tuple[str, str]
  - Główna metoda orchestrująca całe zamknięcie zmian
  - Zwraca ścieżkę do ZIP'a z raportami lub `(None, None)` na błąd
  
- `_close_in_progress_orders(uwagi_lidera)` — zamyka wszystkie bieżące zlecenia w DB
- `_generate_report_files()` → (xls, txt, pdf) — generuje pliki raportów
- `_create_report_zip(xls, txt, pdf)` → str — pakuje raporty do ZIP'a
- `_send_to_outlook(xls_path, uwagi_lidera)` — wysyła raport do Outlooka
- `get_report_files_for_date(date)` → Dict — pobiera istniejące raporty
- `delete_old_reports(days_keep)` → int — czyści stare raporty (domyślnie: 30 dni)

**Przykład użycia:**
```python
from app.services.report_generation_service import ReportGenerationService

# Zamknięcie zmian i generowanie raportów
zip_path, mime_type = ReportGenerationService.close_shift_and_generate_reports('Notatki lidera')
if zip_path:
    return send_file(zip_path, as_attachment=True, mimetype=mime_type)
```

**Testowanie:** 16 jednostkowych testów w `tests/test_report_generation_service.py`

### Struktura tras (Routes)

Aplikacja wykorzystuje blueprinty Flask do organizacji tras:

- `app/blueprints/routes_main.py` — główne trasy (dashboard, zamknięcie zmian)
- `app/blueprints/routes_api.py` — API endpointy
- `app/blueprints/routes_admin.py` — panel administracyjny

Serwisy są wykorzystywane w trasach, co zmniejsza złożoność kontrolerów i ułatwia testowanie.

## 🔒 Zabezpieczenia

- Sesyjne zarządzanie użytkownikami
- Kontrola dostępu oparta na rolach (RBAC)
- Walidacja formularzy po stronie serwera i klienta
- Ochrona przed SQL Injection (parametryzowane zapytania)

## 🧪 Testowanie

Projekt zawiera kompleksowy zestaw testów jednostkowych obejmujący wszystkie warstwy aplikacji.

### Uruchamianie testów

```bash
# Uruchom wszystkie testy (132 testy)
pytest -q

# Uruchom testy z szczegółowym output
pytest -v

# Uruchom testy konkretnego modułu
pytest tests/test_dashboard_service.py -v

# Uruchom testy z pokryciem kodu
pytest --cov=app tests/
```

### Struktura testów

| Moduł | Testy | Opis |
|-------|-------|------|
| `test_auth.py` | 20 | Autentykacja i autoryzacja |
| `test_compat.py` | 23 | Kompatybilność i endpointy |
| `test_middleware.py` | 26 | Middleware i żądania HTTP |
| `test_dashboard_service.py` | 15 | DashboardService (agregacja danych) |
| `test_report_generation_service.py` | 16 | ReportGenerationService (zamknięcie zmian) |
| `test_routes_main.py` | 32 | Główne trasy i integracja |
| **RAZEM** | **132** | **wszystkie przepuszczają** ✅ |

### Pisanie nowych testów

Przykład testowania serwisu:

```python
from unittest.mock import patch, MagicMock
from app.services.dashboard_service import DashboardService

def test_get_production_plans():
    """Test pobierania planów produkcji."""
    with patch('app.services.dashboard_service.get_db_connection') as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value = mock_cursor
        
        result = DashboardService.get_production_plans()
        
        assert isinstance(result, list)
        mock_cursor.execute.assert_called()
```

**Konwencje testowania:**
- Używaj `@pytest.fixture` dla powtarzających się setupów
- Mockuj `get_db_connection()` by uniknąć rzeczywistego połączenia DB
- Testuj na poziomie funkcji publicznych serwisu
- Nienagłośne błędy (graceful degradation) zwracają bezpieczne wartości domyślne

## ⚙️ Konfiguracja

### Zmiana portu aplikacji

Edytuj ostatnią linię w `app.py`:

```python
app.run(debug=True, host='0.0.0.0', port=5000)  # Zmień 5000 na inny port
```

### Tryb produkcyjny

Dla środowiska produkcyjnego ustaw `debug=False`:

```python
app.run(debug=False, host='0.0.0.0', port=5000)
```

### Klucz sesji

Zmień tajny klucz w `app.py` (linia 8):

```python
app.secret_key = 'twoj-losowy-bezpieczny-klucz'
```

## 📝 Funkcje Specjalne

### Auto-Carryover

System automatycznie przenosi niezakończone zlecenia z poprzednich dni na dzień bieżący.

### Walidacja Zgłoszeń

- Minimalny opis problemu: 150 znaków (tylko litery i cyfry)
- Blokada zgłaszania po godzinie 15:00
- Automatyczne uzupełnianie godziny bieżącej

### Przejścia/Zmiany

System pozwala na oznaczanie przerw w produkcji jako "PRZEJŚCIE / ZMIANA".

Funkcja ta może automatycznie zamykać poprzednie zlecenie po rozpoczęciu nowego.

## 🐛 Rozwiązywanie Problemów

### Błąd połączenia z bazą

Sprawdź:

- Czy serwer MySQL jest uruchomiony
- Poprawność danych w `db_config`
- Czy baza `biblioteka` została utworzona
- Uprawnienia użytkownika do bazy

### Błąd importu modułów

Zainstaluj brakujące pakiety:

```bash
pip install -r requirements.txt
```

## 🧰 Development (zalecane: Python 3.11)

Jeśli rozwijasz projekt lokalnie lub uruchamiasz testy, użyj Pythona 3.11.

Wiele binarnych wheel'y dla `numpy` i `pandas` jest dostępnych dla 3.11 na Windows,
co eliminuje konieczność kompilacji C-extensionów.

Krótkie kroki (Windows PowerShell):

```powershell
# 1. Sprawdź czy masz py launcher i Python 3.11
py -0p
py -3.11 -V

# 2. Utwórz virtualenv z Python 3.11
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Zaktualizuj narzędzia instalacyjne i zainstaluj zależności
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Uruchom testy
pytest -q

# 5. Uruchom serwer (w nowym oknie terminala)
python app.py
```

Alternatywa: jeśli używasz `conda`, utwórz środowisko `conda` z Pythonem 3.11
i zainstaluj zależności tam.

### Architektura dla Developerów

Projekt organizuje kod w logiczne warstwy:

```
app/
├── blueprints/           # Trasy Flask (REST API, web endpoints)
│   ├── routes_main.py    # Główne trasy (dashboard, zamknięcie zmian)
│   ├── routes_api.py     # API endpointy
│   └── routes_admin.py   # Panel administracyjny
├── services/             # Serwisy (business logic)
│   ├── dashboard_service.py      # Agregacja danych dashboardu
│   └── report_generation_service.py  # Orchestracja zamknięcia zmian
├── config.py             # Konfiguracja aplikacji
├── db.py                 # Operacje bazy danych
├── decorators.py         # Dekoratory (login_required, roles_required)
└── __init__.py           # Inicjalizacja aplikacji
```

**Wzorzec: Request → Route → Service → Database**

1. HTTP request wchodzi do `route` w blueprincie
2. Route parsuje dane wejściowe i waliduje
3. Route wywołuje odpowiednią metodę `service`
4. Service orchestruje logikę biznesową
5. Service korzysta z `get_db_connection()` by wykonać operacje DB
6. Service zwraca wynik do route'u
7. Route zwraca odpowiedź HTTP

**Przykład: Zamknięcie zmian**

```python
# routes_main.py - trasa
@main_bp.route('/zamknij_zmiane', methods=['POST'])
@roles_required('lider', 'admin')
def zamknij_zmiane():
    uwagi_lidera = request.form.get('uwagi_lidera', '')
    zip_path, mime_type = ReportGenerationService.close_shift_and_generate_reports(uwagi_lidera)
    if zip_path:
        return send_file(zip_path, as_attachment=True, mimetype=mime_type)
    return redirect('/login')

# services/report_generation_service.py - serwis
class ReportGenerationService:
    @staticmethod
    def close_shift_and_generate_reports(uwagi_lidera=''):
        ReportGenerationService._close_in_progress_orders(uwagi_lidera)
        xls_path, txt_path, pdf_path = ReportGenerationService._generate_report_files()
        ReportGenerationService._send_to_outlook(xls_path, uwagi_lidera)
        zip_path = ReportGenerationService._create_report_zip(xls_path, txt_path, pdf_path)
        return (zip_path, 'application/zip') if zip_path else (None, None)
```

### Problemy z kodowaniem

Upewnij się, że baza używa `utf8mb4`:

```sql
ALTER DATABASE biblioteka CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 📄 Licencja

Ten projekt jest własnością Agronetzwerk.

## 👨‍💻 Kontakt

Dla wsparcia technicznego skontaktuj się z administratorem systemu.

---

**Wersja**: 2.0 — Service-Oriented Architecture

**Data ostatniej aktualizacji**: 2026-02-07

**Status**: ✅ 132 testów jednostkowych przechodzące
