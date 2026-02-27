#!/usr/bin/env python3
"""
Prosty backup bazy do pliku .sql (zrzut CREATE TABLE + INSERTy)

Użycie:
  python scripts/backup_database.py --out backups/db-backup.sql

Plik używa konfiguracji z `app.config.DB_CONFIG`.
"""
import os
import argparse
from datetime import datetime
from app.config import DB_CONFIG
from app.db import get_db_connection


def sql_escape(val):
    if val is None:
        return 'NULL'
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, bytes):
        return "'\\x" + val.hex() + "'"
    # dates, datetimes, times -> str
    s = str(val)
    s = s.replace('\\', '\\\\').replace("'", "\\'")
    return f"'{s}'"


def dump_database(out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(f"-- Backup database {DB_CONFIG.get('database')} created at {datetime.now().isoformat()}\n")
        fh.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

        # list tables
        cursor.execute('SHOW TABLES')
        tables = [r[0] for r in cursor.fetchall()]

        for table in tables:
            fh.write(f"--\n-- Table structure for {table}\n--\n\n")
            # DROP
            fh.write(f"DROP TABLE IF EXISTS `{table}`;\n")
            # SHOW CREATE
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            row = cursor.fetchone()
            if row and len(row) >= 2:
                create_sql = row[1]
                fh.write(create_sql + ";\n\n")

            # Dump data
            fh.write(f"--\n-- Data for table {table}\n--\n\n")
            cursor.execute(f"SELECT * FROM `{table}`")
            rows = cursor.fetchall()
            if not rows:
                fh.write('\n')
                continue

            cols = [d[0] for d in cursor.description]
            col_list = ', '.join([f'`{c}`' for c in cols])

            batch_size = 200
            for i in range(0, len(rows), batch_size):
                chunk = rows[i:i+batch_size]
                values_sql = []
                for r in chunk:
                    vals = ', '.join(sql_escape(v) for v in r)
                    values_sql.append(f"({vals})")
                insert_sql = f"INSERT INTO `{table}` ({col_list}) VALUES\n" + ',\n'.join(values_sql) + ";\n"
                fh.write(insert_sql)
            fh.write('\n')

        fh.write('SET FOREIGN_KEY_CHECKS=1;\n')

    cursor.close()
    conn.close()
    print(f'[OK] Backup zapisano do: {out_path}')


def main():
    parser = argparse.ArgumentParser()
    default_name = f"db-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sql"
    default_path = os.path.join('backups', default_name)
    parser.add_argument('--out', '-o', default=default_path, help='Plik wyjściowy dla backupu (.sql)')
    args = parser.parse_args()
    out = args.out
    dump_database(out)


if __name__ == '__main__':
    main()
