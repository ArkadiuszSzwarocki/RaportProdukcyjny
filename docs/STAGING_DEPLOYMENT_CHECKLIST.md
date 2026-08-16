# Staging deployment checklist

Krótkie kroki do wdrożenia zmian na środowisko `staging` oraz sanity checks.

1. Przygotowanie

- Upewnij się, że masz dostęp do bazy staging i konta z uprawnieniami DDL/DML.
- Zrób snapshot/backup DB (użyj `mysqldump` lub mechanizmu cloud provider).

1. Backup (zalecane)

- Lokalnie na maszynie, uruchom:

```bash
./scripts/run_staging_migration.sh <HOST> <PORT> <USER> <DB> <PASSWORD>
```

Skrypt wykona backup do
`backups/staging-backup-<timestamp>.sql` przed uruchomieniem SQL migracji.

1. Suchy przebieg (opcjonalny)

- Na kopii bazy uruchom `scripts/staging_migration.sql` ręcznie i sprawdź wyniki.

1. Wykonanie migracji

- Jeśli backup jest OK, uruchom `run_staging_migration.sh` (patrz wyżej).
- Monitoruj output i logi serwera DB.

1. Restart aplikacji

- Po udanej migracji zrestartuj usługę aplikacyjną.

  Może to być `systemd`, `docker-compose` lub `k8s` (rollout zależnie od infra).

1. Sanity checks

- Ustaw `STAGING_URL` i uruchom sanity script:

```bash
export STAGING_URL=https://staging.example.com
python scripts/staging_sanity.py
```

- Ręczne testy:

  - spróbuj stworzyć nowe zlecenie Workowanie
  - sprawdź listę planów
  - weryfikuj logi aplikacji

1. Rollback (jeżeli potrzeba)

- Przywróć backup:

```bash
mysql -h <HOST> -P <PORT> -u <USER> -p<DB_PASSWORD> < <backups/staging-backup-YYYYMMDDHHMMSS.sql>
```

1. CI / Notatki

- Po udanym wdrożeniu zaimplementuj w CI uruchamianie sanity checks i testów integracyjnych.

---
Jeśli chcesz, mogę przygotować PR z tym skryptem i checklistą.
Mogę też dodać dodatkowy skrypt deduplikacji w Pythonie dla większej kontroli kroków.
