# Copilot / Agent instructions — RaportProdukcyjny

Krótko: ten plik zawiera praktyczne wskazówki dla AI-copilota/agenta, aby być produktywnym w tym repozytorium.

1) Cel projektu
- Backend Flask do zarządzania planami produkcji, zgłoszeniami i raportami.
- Kluczowe moduły: [`app.py`](app.py), blueprinty w [`routes_api.py`](routes_api.py) i [`routes_admin.py`](routes_admin.py), logika DB w [`db.py`](db.py), konfiguracja w [`config.py`](config.py).

2) Architektura — najważniejsze fakty
- Aplikacja tworzy instancję Flask w `app.py` i rejestruje blueprinty: `admin_bp`, `api_bp`, `planista_bp`.
- Połączenie z bazą: moduł `db.py` korzysta z `mysql-connector-python` i dostarcza `get_db_connection()` oraz `setup_database()` (automatyczne migracje przy starcie, chyba że uruchomiono testy — `PYTEST_CURRENT_TEST`).
- Pliki szablonów: `templates/`; statyczne: `static/`; wygenerowane raporty trafiają do `raporty/`.
- Asynchroniczne zadania / wątki: w `app.py` są dwa demony (czyszczenie starych raportów i monitor palet). Zwróć uwagę na skutki side-effectów przy uruchamianiu kodu w testach.

3) Kluczowe konwencje i wzorce kodu
- SQL: używamy parametryzowanych zapytań `cursor.execute(sql, (params,))` z placeholderem `%s` — nie interpoluj stringów bezpośrednio.
- DB access: zawsze używaj `db.get_db_connection()` (testy monkeypatchują tę funkcję).
- RBAC: uprawnienia ról są czytane z `config/role_permissions.json`; kod może czytać config dwojako (z `app.root_path` lub względem pliku), pamiętaj o tej różnicy przy edycji.
- Logowanie: centralny logger zapisuje do `logs/app.log`, dodatkowy `palety.log` dla przypomnień.
- Blueprints: dodawaj nowe endpointy w istniejących blueprintach, rejestracja odbywa się w `app.py`.
- Dekoratory: używaj `@login_required`, `@roles_required(...)`, `@admin_required` z `decorators.py`.

4) Developer workflows (szybkie komendy)
- Utworzenie środowiska i instalacja:
  - `python -m venv .venv` then activate and `pip install -r requirements.txt`
- Uruchomienie aplikacji lokalnie:
  - `python app.py` (dev) — app automatycznie wykona `db.setup_database()` jeśli nie wykryje pytest
  - alternatywnie użyj serwera WSGI (np. `waitress`) w produkcji
- Testy:
  - `pytest -q` — testy oczekują, że kod używa `db.get_db_connection()` tak, by można było monkeypatchować połączenie

5) Bezpieczeństwo i środowisko
- Konfiguracja DB i `SECRET_KEY` z `.env` (wczytywane przez `python-dotenv` w `config.py`).
- Provisioning konta admin: `INITIAL_ADMIN_PASSWORD` env var jest używane przy migracji w `db.setup_database()` — jeśli nie ma tej zmiennej, konto nie jest tworzone automatycznie.

6) Co warto sprawdzić przed zmianami wpływającymi na DB
- Modyfikacje schematu: aktualizuj `db.setup_database()` zamiast ręcznych ALTERów w wielu miejscach — to centralne miejsce migracji/kreacji tabel.
- `routes_admin.py` tworzy backupy `config/role_permissions.json` przy zapisie — szukaj tam przykładów bezpiecznego zapisu plików i backupów.

7) Przykłady szybkich zadań implementacyjnych
- Dodać API endpoint obsługujący nowe pole w `plan_produkcji`: przykładowo — dodaj route w `routes_api.py`, użyj `get_db_connection()`, parametryzuj SQL, commit i close po operacji.
- Dodać walidację wejścia: sprawdź `utils/validation.py` — projekt korzysta z helperów (`require_field`).

8) Gdzie szukać konkretnych przykładów
- Inne istotne pliki: [`routes_api.py`](routes_api.py), [`routes_admin.py`](routes_admin.py), [`db.py`](db.py), [`config.py`](config.py), [`README.md`](README.md).

9) Czego agent NIE powinien robić automatycznie
- Nie zakładaj danych produkcyjnych ani nie tworzyć kont admin bez jawnej zgody (nie ustawiaj haseł w repo).
- Nie uruchamiaj migracji na produkcyjnej bazie bez wyraźnej instrukcji użytkownika.

Proszę o feedback — czy chcesz, abym rozszerzył sekcję z przykładami kodu (szablony commitów/PR), lub dodał checklistę do PR-ów dla zmian DB i bezpieczeństwa?
