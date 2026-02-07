#!/usr/bin/env python3
"""
Simple migration runner that applies SQL files from scripts/migrations.
- Uses `mysql` CLI. Configure connection via env vars: DB_HOST, DB_USER, DB_PASS, DB_NAME, MYSQL_CMD
- Creates table `schema_migrations` to track applied files.
- Applies `*.sql` files (skips `*.down.sql`).
- Supports `--down <migration_filename>` to run a corresponding `.down.sql` rollback and remove record.

Usage:
  DB_USER=user DB_PASS=pass DB_NAME=dbname python scripts/run_migrations.py
  python scripts/run_migrations.py --down 0001_add_wyjscie_columns

Note: This script shells out to the `mysql` CLI. Ensure `mysql` is installed and on PATH.
"""
import os
import sys
import subprocess
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'
MYSQL_CMD = os.environ.get('MYSQL_CMD', 'mysql')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER')
DB_PASS = os.environ.get('DB_PASS')
DB_NAME = os.environ.get('DB_NAME')

if not DB_USER or not DB_NAME:
    print('Please set DB_USER and DB_NAME environment variables (DB_PASS optional).')
    sys.exit(2)

def mysql_base_args():
    args = [MYSQL_CMD, '-h', DB_HOST, '-u', DB_USER]
    if DB_PASS is not None and DB_PASS != '':
        # pass without space to avoid prompt; user should be aware of security implications
        args.append(f"-p{DB_PASS}")
    else:
        # prompt for password if needed
        args.append('-p')
    args.append(DB_NAME)
    return args

def run_sql_file(path: Path):
    print(f"Applying {path.name}...")
    with path.open('rb') as fh:
        proc = subprocess.run(mysql_base_args(), stdin=fh)
    return proc.returncode == 0

def run_sql_string(sql: str):
    proc = subprocess.run(mysql_base_args() + ['-e', sql])
    return proc.returncode == 0

def ensure_migrations_table():
    sql = (
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "filename VARCHAR(255) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB;"
    )
    return run_sql_string(sql)

def get_applied():
    proc = subprocess.run(mysql_base_args() + ['-N', '-B', '-e', "SELECT filename FROM schema_migrations;"], capture_output=True, text=True)
    if proc.returncode != 0:
        return set()
    out = proc.stdout.strip().splitlines()
    return set(x.strip() for x in out if x.strip())

def record_applied(fname: str):
    sql = "INSERT INTO schema_migrations (filename) VALUES (%s);".replace('%s', f"'{fname.replace("'","''")}'")
    return run_sql_string(sql)

def remove_record(fname: str):
    sql = "DELETE FROM schema_migrations WHERE filename = %s;".replace('%s', f"'{fname.replace("'","''")}'")
    return run_sql_string(sql)

def list_migration_files():
    files = sorted([f for f in MIGRATIONS_DIR.glob('*.sql') if not f.name.endswith('.down.sql')])
    return files

def apply_all():
    if not ensure_migrations_table():
        print('Failed to ensure schema_migrations table exists.')
        return 1
    applied = get_applied()
    files = list_migration_files()
    to_apply = [f for f in files if f.name not in applied]
    if not to_apply:
        print('No new migrations to apply.')
        return 0
    for f in to_apply:
        ok = run_sql_file(f)
        if not ok:
            print(f'Failed to apply {f.name}. Stopping.')
            return 2
        if not record_applied(f.name):
            print(f'WARNING: applied {f.name} but failed to record it in schema_migrations.')
    print('Migrations applied successfully.')
    return 0

def rollback(migration_basename: str):
    down_name = migration_basename + '.down.sql' if not migration_basename.endswith('.down') else migration_basename
    down_file = MIGRATIONS_DIR / down_name
    if not down_file.exists():
        print(f'Rollback file not found: {down_file}')
        return 2
    ok = run_sql_file(down_file)
    if not ok:
        print(f'Failed to execute rollback {down_file.name}')
        return 3
    # remove record if present
    if not remove_record(migration_basename if not migration_basename.endswith('.down.sql') else migration_basename.replace('.down.sql','')):
        print('Warning: failed to remove migration record from schema_migrations (it may not have been recorded).')
    print('Rollback executed.')
    return 0

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--down', help='Rollback given migration basename (e.g. 0001_add_wyjscie_columns)')
    args = p.parse_args()
    if args.down:
        sys.exit(rollback(args.down))
    sys.exit(apply_all())
