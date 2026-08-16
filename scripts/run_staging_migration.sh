#!/usr/bin/env bash
# run_staging_migration.sh
# Usage: ./run_staging_migration.sh MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_DB MYSQL_PWD
# This script performs a backup using mysqldump and then runs the migration SQL.

HOST=${1:-localhost}
PORT=${2:-3306}
USER=${3:-root}
DB=${4:-raport}
PWD=${5}
SQL_FILE="$(dirname "$0")/staging_migration.sql"

if [ -z "$PWD" ]; then
  echo "ERROR: Please supply DB password as 5th argument or set MYSQL_PWD environment variable."
  exit 1
fi

TIMESTAMP=$(date +%Y%m%d%H%M%S)
BACKUP_FILE="backups/staging-backup-$TIMESTAMP.sql"

mkdir -p backups

echo "Creating backup to $BACKUP_FILE..."
mysqldump -h "$HOST" -P "$PORT" -u "$USER" -p"$PWD" "$DB" > "$BACKUP_FILE"
if [ $? -ne 0 ]; then
  echo "Backup failed. Aborting."
  exit 2
fi

echo "Running migration SQL: $SQL_FILE"
mysql -h "$HOST" -P "$PORT" -u "$USER" -p"$PWD" "$DB" < "$SQL_FILE"
if [ $? -ne 0 ]; then
  echo "Migration failed. Check logs and consider restoring backup: $BACKUP_FILE"
  exit 3
fi

echo "Migration finished. Backup at: $BACKUP_FILE"
exit 0
