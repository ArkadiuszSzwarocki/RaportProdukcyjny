# RaportProdukcyjny

System webowy Flask do obsługi produkcji, magazynu, planowania, jakości, raportowania, skanowania kodów oraz procesów paletowych.

## Główne moduły

- planowanie i realizacja produkcji;
- gospodarka magazynowa dla surowców, opakowań i wyrobów gotowych;
- kompletacja FIFO i kalkulator zapotrzebowania;
- przyjęcia, przesunięcia, skanery QR/SSCC i inwentaryzacja;
- raporty jakości, HR i raporty zmianowe;
- druk etykiet przez lokalny, uwierzytelniony mostek druku;
- role i uprawnienia użytkowników.

## Wymagania

- Python 3.11;
- MySQL 8 / zgodna instancja MySQL;
- `pip`;
- opcjonalnie Docker lub Kubernetes.

## Instalacja lokalna

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Skopiuj `.env.example` do `.env` i ustaw wartości właściwe dla środowiska. Dane dostępowe, klucze szyfrujące, adresy infrastruktury i tokeny nie powinny być zapisywane w repozytorium.

Minimalna konfiguracja:

```dotenv
FLASK_ENV=development
SECRET_KEY=<losowy-klucz-minimum-32-znaki>
ENCRYPTION_KEY=<klucz-Fernet>
DB_HOST=localhost
DB_PORT=3306
DB_USER=<uzytkownik-aplikacyjny>
DB_PASSWORD=<haslo>
DB_NAME=<nazwa-bazy>
ENABLE_BACKGROUND_DAEMONS=true
```

Uruchomienie developerskie:

```bash
python app.py
```

Produkcja używa Gunicorna zgodnie z `gunicorn.conf.py` i `wsgi.py`.

## Bezpieczeństwo konfiguracji

W produkcji wymagane są:

- unikalny `SECRET_KEY` minimum 32 znaki;
- osobny `ENCRYPTION_KEY` Fernet;
- osobne hasła administratora MySQL i użytkownika aplikacyjnego;
- TLS na reverse proxy / Ingress;
- `TRUST_PROXY_HEADERS=true` tylko za rzeczywiście zaufanym proxy;
- drukarki i ich adresy konfigurowane przez środowisko, nie w kodzie;
- `PRINTER_BRIDGE_TOKEN` dla mostka druku;
- sekrety w secret store, a nie w plikach śledzonych przez Git.

Aplikacja stosuje DB-backed session tracking, fail-closed validation sesji, kontrolę ról, ochronę same-origin dla żądań modyfikujących i ograniczenie zaufania do nagłówków proxy.

## Mostek druku

Mostek `printer_server/server.py` domyślnie nasłuchuje tylko na `127.0.0.1`. Przy udostępnieniu poza localhost wymagany jest token i jawna lista drukarek.

Przykładowa konfiguracja:

```dotenv
PRINTER_BRIDGE_URL=http://127.0.0.1:3001
PRINTER_BRIDGE_TOKEN=<dlugi-losowy-token>
PRINTER_IP_MAP_JSON={"Warehouse":"10.0.0.10"}
PRINTER_BRIDGE_HOST=127.0.0.1
PRINTER_BRIDGE_PORT=3001
```

Nie przekazuj dowolnego `IP:PORT` z przeglądarki. Mostek akceptuje wyłącznie cele znajdujące się w skonfigurowanej allowliście.

## Testy i CI

```bash
pytest -q
pytest --cov=app --cov-report=term-missing
```

CI wykonuje m.in. testy Pythona, lint, kontrolę typów, build obrazu Docker oraz skan podatności Trivy.

## Docker

```bash
docker build -t raportprodukcyjny:local .
```

Kontener działa jako użytkownik nie-root. W środowisku produkcyjnym TLS powinien być terminowany przed aplikacją, np. na Ingressie lub reverse proxy.

## Kubernetes

Instrukcja wdrożenia znajduje się w `k8s/README.md`.

Ważne zasady:

- `app-secrets` tworzony jest poza repozytorium;
- MySQL działa wewnętrznie na porcie `3306`;
- aplikacja jest wystawiana przez `ClusterIP` + Ingress;
- web workers nie uruchamiają własnych daemonów;
- jeden dedykowany Deployment `app-daemons` obsługuje procesy tła;
- ServiceAccount nie ma dostępu do Secrets/ConfigMaps przez Kubernetes API.

## Struktura projektu

```text
app/                 aplikacja Flask, blueprints, serwisy i repozytoria
printer_server/      lokalny mostek druku
templates/           szablony HTML
static/              zasoby frontendowe
scripts/             aktywne skrypty operacyjne
k8s/                 manifesty Kubernetes
tests/               testy automatyczne
.github/workflows/   CI/CD
```

## Zasady rozwoju

- nie umieszczaj sekretów, haseł, tokenów ani prywatnych adresów infrastruktury w kodzie;
- używaj parametryzowanych zapytań SQL dla wartości;
- identyfikatory tabel dynamicznych pobieraj wyłącznie przez istniejące mapowanie/allowlisty;
- nowe endpointy modyfikujące dane powinny wymagać uwierzytelnienia i przechodzić ochronę CSRF/same-origin;
- operacje sieciowe muszą mieć timeout i weryfikację TLS;
- dla nowych funkcji biznesowych dodawaj testy regresyjne.
