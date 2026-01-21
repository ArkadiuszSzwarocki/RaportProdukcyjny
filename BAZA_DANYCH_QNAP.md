# Konfiguracja Bazy Danych QNAP

## Dane Połączenia

```text
Host: filipinka.myqnapcloud.com
Port: 3307
Użytkownik: rootMlecznaDroga
Hasło: Filipinka2025
Baza: MleczDroga
```

## Struktury Plików Konfiguracyjnych

### Backend (.env)

Plik `.env` w katalogu głównym zawiera zmienne środowiskowe dla backendu:

```env
PORT=8089
DB_HOST=filipinka.myqnapcloud.com
DB_PORT=3307
DB_USER=rootMlecznaDroga
DB_PASSWORD=Filipinka2025
DB_NAME=MleczDroga
```

**Lokalizacja:** `/workspaces/Mleczna-droga/.env`

### Frontend (.env.local)

Plik `.env.local` zawiera zmienne dla frontendu (Vite):

```env
VITE_API_URL=http://localhost:8089/api
```

**Lokalizacja:** `/workspaces/Mleczna-droga/.env.local`

**Dla połączenia z zdalnym QNAP zmień na:**

```env
VITE_API_URL=http://filipinka.myqnapcloud.com:8089/api
```

## Zmienne Środowiskowe

### Backend (server.js)

Backend automatycznie czyta zmienne z `.env`:

- `DB_HOST` - adres hosta bazy danych
- `DB_PORT` - port (domyślnie 3307)
- `DB_USER` - użytkownik
- `DB_PASSWORD` - hasło
- `DB_NAME` - nazwa bazy danych
- `PORT` - port serwera API (domyślnie 5000)

### Frontend (constants.ts)

Frontend czyta zmienną `VITE_API_URL` w `constants.ts`:

```typescript
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8089/api';
```

## Uruchamianie

### Tylko backend (połączony z QNAP)

```bash
npm run backend
```

### Tylko frontend

```bash
npm run frontend
```

### Oba jednocześnie (dev mode)

```bash
npm run dev
```

## Sprawdzanie Połączenia

### Health Check (backend)

```bash
curl http://localhost:8089/api/health
```

Prawidłowa odpowiedź:

```json
{
  "status": "OK",
  "database": "connected",
  "host": "filipinka.myqnapcloud.com",
  "timestamp": "2026-01-03T13:..."
}
```

## Przełączanie między Localhost a QNAP

### Dla pracy lokalnej

1. **Backend** - zostaw domyślnie na localhost (domyślnie w `.env`)
2. **Frontend** - zmień `.env.local`:

```env
VITE_API_URL=http://localhost:8089/api
```

### Dla połączenia z QNAP

1. **Backend** - zmień `.env`:

```env
DB_HOST=filipinka.myqnapcloud.com
```

2. **Frontend** - zmień `.env.local`:

```env
VITE_API_URL=http://filipinka.myqnapcloud.com:8089/api
```

## Bezpieczeństwo

⚠️ **WAŻNE:** Nie commituj pliku `.env` z hasłami do repozytorium!

Dodaj `.env` do `.gitignore`:

```
.env
.env.local
.env.*.local
```

## Troubleshooting

### Błąd: "connect ECONNREFUSED"

- Sprawdź czy backend jest uruchomiony na porcie 8089
- Sprawdź czy QNAP jest dostępny (ping filipinka.myqnapcloud.com)
- Sprawdź czy dane logowania są prawidłowe

### Błąd: "getaddrinfo ENOTFOUND"

- Sprawdź połączenie internetowe
- Sprawdź czy URL jest prawidłowy: `filipinka.myqnapcloud.com`

### CORS Errors

- Backend ma już zdefiniowany CORS (`cors` middleware w server.js)
- Jeśli problem persystuje, sprawdź czy backend jest dostępny

## Architektura

```
┌─────────────────────┐
│   Frontend (Vite)   │
│   constants.ts      │
│ VITE_API_URL        │
└──────────┬──────────┘
           │
           │ HTTP
           ▼
┌─────────────────────┐
│  Backend (Node.js)  │
│  server.js          │
│  Port: 8089         │
└──────────┬──────────┘
           │
           │ TCP/IP
           ▼
┌─────────────────────┐
│   QNAP (MariaDB)    │
│ 3307 (MySQL API)    │
│ filipinka.myqnap... │
└─────────────────────┘
```

## Zapytania do Bazy Danych

### Przykładowe zapytania SQL

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='MleczDroga'
  AND TABLE_NAME IN ('inventory_sessions','inventory_snapshots','inventory_scans');
```

### Tworzenie kopii zapasowej tabeli `inventory_sessions`

```sql
CREATE TABLE inventory_sessions_backup LIKE inventory_sessions;
INSERT INTO inventory_sessions_backup SELECT * FROM inventory_sessions;
```

### Zmiana silnika i kodowania tabeli `inventory_sessions`

```sql
ALTER TABLE inventory_sessions ENGINE=InnoDB, CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Required secrets (GitHub Actions)

Jeżeli używamy automatycznego deploymentu przez GitHub Actions (plik `.github/workflows/deploy-to-qnap.yml`), repozytorium musi mieć skonfigurowane poniższe *Secrets* w ustawieniach GitHub (`Settings → Secrets → Actions`):

- `REGISTRY_HOST` — adres rejestru (np. `ghcr.io` lub `registry.example.com`)
- `REGISTRY_USERNAME` — nazwa użytkownika do rejestru
- `REGISTRY_PASSWORD` — hasło/token do rejestru
- `REGISTRY_REPOSITORY` — pełna nazwa repozytorium obrazu (np. `owner/repo`)
- `QNAP_HOST` — host QNAP (np. `filipinka.myqnapcloud.com`)
- `QNAP_USER` — użytkownik SSH na QNAP (np. `admin`)
- `QNAP_SSH_PRIVATE_KEY` — prywatny klucz SSH (warto ustawić jako *private* secret)
- `QNAP_CONTAINER_NAME` — nazwa kontenera Docker na QNAP
- `QNAP_APP_PORT` — port, na którym ma być wystawiona aplikacja (np. `8089`)
- `QNAP_SSH_PORT` — opcjonalny port SSH (domyślnie `22`)

Uwaga: nie umieszczaj w repozytorium haseł ani kluczy prywatnych. Dodaj je jako Secrets, a workflow będzie ich bezpiecznie używał.
