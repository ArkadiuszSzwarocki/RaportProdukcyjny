# Uruchamianie aplikacji i mostka druku

Aplikacja może korzystać z dwóch procesów:

1. głównej aplikacji Flask/Gunicorn;
2. lokalnego mostka druku `printer_server/server.py`.

## Aplikacja WWW

Development:

```bash
python app.py
```

Produkcja:

```bash
gunicorn -c gunicorn.conf.py wsgi:app
```

Konfiguracja pochodzi z `.env` / sekretów środowiska. Nie wpisuj adresów infrastruktury ani haseł bezpośrednio do kodu.

## Mostek druku

Mostek domyślnie działa tylko na loopback:

```dotenv
PRINTER_BRIDGE_HOST=127.0.0.1
PRINTER_BRIDGE_PORT=3001
PRINTER_BRIDGE_TOKEN=<dlugi-losowy-token>
PRINTER_IP_MAP_JSON={"Warehouse":"10.0.0.10"}
```

Uruchomienie:

```bash
python printer_server/server.py
```

Jeśli mostek ma nasłuchiwać poza localhost, `PRINTER_BRIDGE_TOKEN` jest obowiązkowy. Dostępne drukarki muszą być podane w `PRINTER_IP_MAP_JSON`; żądanie HTTP nie może wybrać dowolnego hosta lub portu.

## TLS

Najprostszy i zalecany wariant to TLS zakończony na reverse proxy / Ingressie. Jeżeli sam mostek druku ma używać HTTPS, podaj prawdziwy certyfikat i klucz:

```dotenv
PRINTER_BRIDGE_TLS_CERT=/secure/path/bridge-cert.pem
PRINTER_BRIDGE_TLS_KEY=/secure/path/bridge-key.pem
```

Klient aplikacji domyślnie weryfikuje certyfikat. Dla prywatnego CA użyj:

```dotenv
PRINTER_BRIDGE_CA_BUNDLE=/secure/path/company-ca.pem
```

## Procesy tła

W produkcji web workers powinny mieć:

```dotenv
ENABLE_BACKGROUND_DAEMONS=false
```

Daemony uruchamiaj w dokładnie jednym dedykowanym procesie:

```bash
ENABLE_BACKGROUND_DAEMONS=true SKIP_DB_SETUP=true python scripts/run_daemons.py
```

Manifesty Kubernetes robią to automatycznie przez osobny Deployment `app-daemons`.

## Diagnostyka

Status mostka:

```text
GET /status
```

Pozostałe endpointy mostka wymagają autoryzacji. Do diagnostyki używaj adresów i nazw drukarek skonfigurowanych lokalnie w środowisku docelowym, nie wartości wpisanych do repozytorium.
