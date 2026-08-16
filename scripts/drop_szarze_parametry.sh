#!/usr/bin/env bash
# Skrypt pomocniczy do wykonania pliku SQL usuwającego tabelę szarze_parametry
# Uwaga: wymaga dostępu do mysql client i zmiennych środowiskowych: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

SQL_FILE="$(dirname "$0")/../db-init/02-drop-szarze_parametry.sql"
if [ ! -f "$SQL_FILE" ]; then
  echo "Plik SQL nie istnieje: $SQL_FILE"
  exit 1
fi

if [ -z "$DB_HOST" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ] || [ -z "$DB_NAME" ]; then
  echo "Ustaw zmienne środowiskowe: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME"
  exit 2
fi

mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "$SQL_FILE"
RC=$?
if [ $RC -ne 0 ]; then
  echo "Polecenie mysql zwróciło kod: $RC"
  exit $RC
fi

echo "Skrypt wykonany pomyślnie. Sprawdź bazę, aby potwierdzić usunięcie tabeli." 
