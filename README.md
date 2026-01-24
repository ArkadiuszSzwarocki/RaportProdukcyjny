# Biblioteka - System Zarządzania Produkcją Agronetzwerk

System webowy do zarządzania produkcją, planowaniem i raportowaniem w zakładzie produkcyjnym.

## 📋 Funkcjonalności

### Dla Wszystkich Użytkowników
- ✅ Logowanie z różnymi poziomami uprawnień (Admin, Lider, Planista, Pracownik)
- 📊 Podgląd planu produkcji z podziałem na sekcje (Zasyp, Workowanie, Magazyn)
- 📅 Nawigacja po datach - przeglądanie historii i planowanie przyszłych zdarzeń
- 🚨 Zgłaszanie problemów produkcyjnych (awarie, postoje, mikro-zatrzymania, usterki)
- 👷 Zarządzanie obsadą zmianową

### Dla Planisty
- 📝 Dodawanie planów produkcji
- ✏️ Edycja tonażu planowanego i rzeczywistego
- 📈 Export raportów do Excel
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
cd c:\Users\arkad\Documents\GitHub\Biblioteka
```

2. **Utwórz wirtualne środowisko**
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. **Zainstaluj zależności**
```bash
pip install -r requirements.txt
```

#### Zależności developerskie

Jeśli chcesz uruchamiać testy lokalnie lub w środowisku CI, zainstaluj zależności developerskie:

```bash
pip install -r requirements-dev.txt
```


4. **Skonfiguruj bazę danych**
   
   Edytuj plik `app.py` i dostosuj konfigurację bazy danych (linie 11-18):
```python
db_config = {
    'host': '192.168.0.18',      # Adres serwera MySQL
    'port': 3307,                # Port (domyślnie 3307)
    'database': 'biblioteka',    # Nazwa bazy
    'user': 'biblioteka',        # Użytkownik
    'password': 88888888888888, # Hasło
    'charset': 'utf8mb4'
}
```

5. **Uruchom aplikację**
```bash
python app.py
```

Aplikacja będzie dostępna pod adresem: `http://localhost:5000`



## 🗄️ Struktura Bazy Danych

System automatycznie tworzy następujące tabele:

- **pracownicy** - lista pracowników
- **uzytkownicy** - konta logowania
- **dziennik_zmiany** - zgłoszenia problemów/awarii
- **obsada_zmiany** - obsada pracowników na zmianach
- **plan_produkcji** - plany i realizacja produkcji
- **obecnosc** - raportowanie HR (nieobecności/nadgodziny)
- **raporty_koncowe** - zamknięte zmiany z uwagami lidera

## 📊 Moduły Systemu

### 1. Dashboard Produkcji (`/`)
- Podgląd planu produkcji na wybrany dzień
- Śledzenie statusu zleceń (zaplanowane → w toku → zakończone)
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
  - Arkusz "Produkcja" - plan i wykonanie
  - Arkusz "Awarie" - problemy produkcyjne
  - Arkusz "HR" - nieobecności i nadgodziny

## 🔒 Zabezpieczenia

- Sesyjne zarządzanie użytkownikami
- Kontrola dostępu oparta na rolach (RBAC)
- Walidacja formularzy po stronie serwera i klienta
- Ochrona przed SQL Injection (parametryzowane zapytania)

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
System pozwala na oznaczanie przerw w produkcji jako "PRZEJŚCIE / ZMIANA" z automatycznym zamykaniem poprzedniego zlecenia.

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

Jeśli rozwijasz projekt lokalnie lub uruchamiasz testy, użyj Pythona 3.11 (wiele binarnych wheel'y dla `numpy`/`pandas` jest dostępnych dla 3.11 na Windows, co eliminuje konieczność kompilacji C-extensionów).

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

# 4. Uruchom serwer (w nowym oknie terminala)
python app.py

# 5. Uruchom testy w głównym terminalu
pytest -q
```

Alternatywa: jeśli używasz `conda`, utwórz środowisko `conda` z Pythonem 3.11 i zainstaluj zależności tam.


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

**Wersja**: 1.0  
**Data ostatniej aktualizacji**: 2026-01-17
