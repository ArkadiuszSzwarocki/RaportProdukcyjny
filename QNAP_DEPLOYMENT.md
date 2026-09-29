# Uruchomienie na QNAP Container Station

Obraz aplikacji nie zawiera pliku `.env`, bazy MySQL ani haseł. To celowe:
sekrety nie mogą trafić do obrazu publikowanego w GHCR.

Ten projekt używa istniejącej bazy wskazanej w pliku `.env`; nie uruchamia
drugiego, pustego kontenera MySQL.

1. Na QNAP utwórz katalog aplikacji, np. `Container/raportprodukcyjny`.
2. Umieść w nim dwa pliki z repozytorium: `docker-compose.qnap.yml` i swój
   aktualny plik `.env` z działającego środowiska lokalnego.
3. W Container Station utwórz aplikację z pliku `docker-compose.qnap.yml`.
4. Uruchom aplikację. Interfejs będzie dostępny pod portem `5005`.

W `.env` muszą istnieć poprawne wartości `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `SECRET_KEY`, `ENCRYPTION_KEY` i `USE_SSL`.

`docker-compose.qnap.yml` celowo wymusza `FLASK_ENV=production` i
`FLASK_DEBUG=false`, nawet gdy lokalny plik `.env` ma ustawienia developerskie.
Wartość `USE_SSL` pozostaje odczytana z `.env`: dla QNAP z odwrotnym proxy TLS
zwykle kończy się na proxy, więc aplikacja powinna mieć `USE_SSL=false`.

Nie ustawiaj `DB_HOST=localhost`, ponieważ dla kontenera oznacza to jego
własne środowisko, a nie MySQL działający na NAS lub w sieci.

Po uruchomieniu sprawdź log kontenera. Poprawny start nie zawiera komunikatu
`Can't connect to MySQL server on 'localhost:3307'`.

## Aktualizacja aplikacji po commitach na GitHub

1. Przejdź do katalogu aplikacji na QNAP (np. `/share/homes/Arecki`):
```bash
docker compose --env-file .env -f docker-compose.qnap.yml pull
docker compose --env-file .env -f docker-compose.qnap.yml up -d
```
2. Po aktualizacji wyloguj się i zaloguj ponownie w przeglądarce, aby odświeżyć ciasteczko sesji.
