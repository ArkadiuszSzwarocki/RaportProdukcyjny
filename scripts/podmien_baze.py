#!/usr/bin/env python3
"""Bezpieczna procedura podmiany bazy MySQL w środowisku Docker Compose."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


DEFAULT_SQL_FILE = 'nowa_baza.sql'


def _compose_prefix():
    """Return a shell-free Docker Compose command prefix.

    Override with e.g. ``DOCKER_COMPOSE_COMMAND='docker-compose'`` or
    ``DOCKER_COMPOSE_COMMAND='sudo docker compose'`` on the target host.
    ``shlex.split`` only tokenizes configuration; commands are still executed
    with ``shell=False``.
    """
    raw = os.getenv('DOCKER_COMPOSE_COMMAND', 'docker compose').strip()
    parts = shlex.split(raw)
    if not parts:
        raise RuntimeError('DOCKER_COMPOSE_COMMAND nie może być pusty.')
    return parts


def run_cmd(args, *, check=True, stdin_handle=None):
    command = [str(part) for part in args]
    print(f"\n[EXEC] {shlex.join(command)}")
    result = subprocess.run(
        command,
        stdin=stdin_handle,
        check=check,
        shell=False,
    )
    return result.returncode == 0


def compose(*args, check=True, stdin_handle=None):
    return run_cmd(
        [*_compose_prefix(), *args],
        check=check,
        stdin_handle=stdin_handle,
    )


def main():
    parser = argparse.ArgumentParser(
        description='Procedura podmiany bazy danych (Docker Compose / Python)'
    )
    parser.add_argument(
        'sql_file',
        nargs='?',
        default=DEFAULT_SQL_FILE,
        help='Ścieżka pliku zrzutu SQL (domyślnie: nowa_baza.sql)',
    )
    parser.add_argument('--yes', '-y', action='store_true', help='Pomiń pytanie potwierdzające')
    args = parser.parse_args()

    sql_path = Path(args.sql_file).expanduser().resolve()
    if not sql_path.is_file():
        print(f"[BŁĄD] Nie znaleziono pliku SQL: {sql_path}")
        candidates = sorted(Path.cwd().glob('*.sql'))
        if candidates:
            print('Pliki SQL w bieżącym katalogu:')
            for candidate in candidates:
                print(f'  - {candidate.name}')
        sys.exit(1)

    file_size_mb = sql_path.stat().st_size / (1024 * 1024)
    print('======================================================================')
    print('    PROCEDURA PODMIANY BAZY DANYCH (DOCKER COMPOSE)')
    print('======================================================================')
    print(f'Plik: {sql_path} ({file_size_mb:.2f} MB)')

    if not args.yes:
        confirm = input(
            '\nUWAGA: procedura usunie dotychczasowy wolumen bazy. '
            'Kontynuować? (t/N): '
        )
        if confirm.strip().lower() not in {'t', 'tak', 'y', 'yes'}:
            print('Anulowano procedurę.')
            return

    print('\n--- KROK 1: zatrzymanie środowiska i usunięcie wolumenu ---')
    compose('down', '-v')

    print('\n--- KROK 2: uruchomienie czystej bazy ---')
    compose('up', '-d', 'db')

    print('\n--- KROK 3: oczekiwanie na MySQL ---')
    readiness_command = (
        'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
        'exec mysqladmin -u root ping'
    )
    ready = False
    for attempt in range(1, 31):
        try:
            compose(
                'exec', '-T', 'db', 'sh', '-c', readiness_command,
                check=True,
            )
            ready = True
            break
        except subprocess.CalledProcessError:
            print(f'MySQL jeszcze niegotowy ({attempt}/30)...')
            time.sleep(2)
    if not ready:
        raise RuntimeError('MySQL nie osiągnął gotowości w wymaganym czasie.')

    print('\n--- KROK 4: import dumpa SQL ---')
    import_command = (
        'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
        'exec mysql -u root "$MYSQL_DATABASE"'
    )
    # The dump path never enters a shell command. Bytes are streamed directly
    # to mysql stdin, so hostile spaces/quotes in a local filename are harmless.
    with sql_path.open('rb') as sql_stream:
        compose(
            'exec', '-T', 'db', 'sh', '-c', import_command,
            stdin_handle=sql_stream,
        )

    print('\n--- KROK 5: uruchomienie aplikacji ---')
    compose('up', '-d', 'app')

    print('\n======================================================================')
    print('PROCEDURA PODMIANY BAZY DANYCH ZAKOŃCZONA SUKCESEM')
    print('======================================================================')
    print('Zweryfikuj aplikację na adresie skonfigurowanym dla środowiska docelowego.')


if __name__ == '__main__':
    main()
