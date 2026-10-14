# Deployment guide

Ten dokument opisuje aktualny sposób wdrażania `RaportProdukcyjny`. Nie zawiera
historycznych wyników testów ani deklaracji „production ready” — bieżący stan
zawsze należy potwierdzić w GitHub Actions dla dokładnego SHA wdrażanego commita.

## Wymagane sekrety

W produkcji ustaw poza repozytorium co najmniej:

```env
FLASK_ENV=production
SECRET_KEY=<losowy klucz min. 32 znaki>
ENCRYPTION_KEY=<poprawny klucz Fernet>
DB_HOST=<host MySQL>
DB_PORT=3306
DB_NAME=<nazwa bazy>
DB_USER=<dedykowany użytkownik aplikacji>
DB_PASSWORD=<silne hasło aplikacji>
INITIAL_ADMIN_PASSWORD=<silne hasło początkowe>
```

Nie używaj tego samego hasła dla użytkownika aplikacji i `root` MySQL. Plik
`.env` nie może trafić do kontroli wersji.

Jeżeli używany jest mostek drukowania, skonfiguruj również:

```env
PRINTER_BRIDGE_URL=http://127.0.0.1:3001
PRINTER_BRIDGE_TOKEN=<losowy długi token>
PRINTER_IP_MAP_JSON={"Magazyn":"10.0.0.10"}
PRINTER_BRIDGE_ALLOWED_ORIGINS=https://twoja-domena.example
```

Adresy powyżej są przykładami. Rzeczywiste adresy infrastruktury przechowuj w
konfiguracji środowiska.

## Docker Compose

Najprostszy wariant wdrożenia używa pliku `docker-compose.yml`, który wymaga
sekretów przez zmienne środowiskowe.

```bash
docker compose build --pull
docker compose up -d
docker compose ps
```

Aplikacja działa przez Gunicorn. Nie uruchamiaj produkcji przez wbudowany serwer
Flask `python app.py`.

### Kontrola przed wdrożeniem

Przed zmianą wersji produkcyjnej sprawdź dokładny commit:

```bash
python -m pytest -q
python -m pylint --disable=all --enable=E,F app/
docker build -t raportprodukcyjny:verify .
```

W repozytorium obowiązuje również CI na Pythonie 3.10, 3.11 i 3.12 oraz test
obrazu Docker. Wdrażaj dopiero commit, dla którego wymagane workflow zakończyły
się sukcesem.

## Kubernetes

Manifesty znajdują się w `k8s/`.

1. Zastosuj `k8s/00-namespace-config.yaml` — zawiera tylko niesekretne dane.
2. Utwórz `app-secrets` na podstawie `k8s/app-secrets.example.yaml`; nie commituj
   wypełnionego Secretu.
3. Zastosuj MySQL, aplikację/worker daemonów i Ingress/NetworkPolicy zgodnie z
   `k8s/README.md`.
4. Usługa aplikacji jest `ClusterIP`; ruch zewnętrzny powinien przechodzić przez
   kontrolowany Ingress/TLS.
5. MySQL pozostaje usługą wewnętrzną na porcie `3306`.

## Reverse proxy

Aplikacja domyślnie **nie ufa** nagłówkom `X-Forwarded-*`. Jeżeli stoi za
kontrolowanym reverse proxy, ustaw:

```env
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_HOPS=1
```

Nie zwiększaj liczby hopów bez znajomości dokładnej topologii proxy.

## Procesy tła

W produkcji web workers nie uruchamiają automatycznie daemonów. Zadania tła
powinny działać w dedykowanym procesie/deploymencie z:

```env
ENABLE_BACKGROUND_DAEMONS=true
```

Dla zwykłych workerów WWW pozostaw tę opcję wyłączoną.

## TLS i certyfikaty

Nie używaj `verify=False` ani samopodpisanego TLS jako obejścia błędów
certyfikatów. Dla publicznego/firmowego endpointu użyj certyfikatu zaufanego przez
klientów. Lokalny mostek drukowania może działać po HTTP na loopback, ponieważ
jest dodatkowo chroniony tokenem i nie powinien być publicznie wystawiany.

## Backup i rollback

Przed migracją lub podmianą bazy wykonaj zweryfikowaną kopię zapasową. Narzędzie
`scripts/podmien_baze.py` używa Docker Compose bez `shell=True` i strumieniuje
plik SQL do kontenera przez stdin; nadal jest to operacja destrukcyjna i wymaga
świadomego potwierdzenia.

Rollback aplikacji powinien wskazywać poprzedni, wcześniej przetestowany tag/SHA
obrazu. Rollback schematu bazy wymaga osobnej procedury i kopii danych.

## Checklista produkcyjna

- [ ] Wszystkie wymagane workflow dla wdrażanego SHA są zielone.
- [ ] `SECRET_KEY`, `ENCRYPTION_KEY` i hasła DB są ustawione poza repozytorium.
- [ ] Aplikacja korzysta z dedykowanego użytkownika MySQL, nie z `root`.
- [ ] TLS/reverse proxy są skonfigurowane zgodnie z topologią środowiska.
- [ ] Mostek drukowania ma token i allowlistę drukarek/originów.
- [ ] Daemony działają tylko w dedykowanym procesie.
- [ ] Backup bazy został wykonany i sprawdzony.
- [ ] Monitoring/logi nie ujawniają sekretów ani tokenów w URL.
