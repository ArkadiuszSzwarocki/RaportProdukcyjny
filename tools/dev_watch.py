import os
import sys
import time
import subprocess
from pathlib import Path

WATCH_DIR = Path(__file__).resolve().parents[1]
IGNORE_DIRS = {'.venv', '__pycache__', '.git'}
POLL_INTERVAL = 1.0


def iter_py_files(root):
    for p in root.rglob('*.py'):
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        yield p


def snapshot():
    return {p: p.stat().st_mtime for p in iter_py_files(WATCH_DIR)}


def run_tests():
    # Testy zostały wyłączone na prośbę użytkownika.
    print('\n[dev_watch] Pomijanie testów pytest (zgodnie z ustawieniem)...')
    return 0


def restart_server():
    """Call PowerShell restart script on Windows. No-op on other platforms."""
    script = WATCH_DIR / 'scripts' / 'restart_server.ps1'
    if not script.exists():
        print('[dev_watch] restart script not found:', script)
        return 1
    if os.name == 'nt':
        cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Port', '8082', '-Retries', '3']
    else:
        print('[dev_watch] Non-Windows platform: manual restart required')
        return 1
    print('[dev_watch] Running restart script...')
    r = subprocess.run(cmd, cwd=str(WATCH_DIR))
    print('[dev_watch] restart script exit code:', r.returncode)
    return r.returncode


def main():
    print('Starting dev watcher in', WATCH_DIR)
    last = snapshot()
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            cur = snapshot()
            if cur != last:
                changed = [str(p) for p in cur.keys() if p not in last or cur[p] != last[p]]
                print('Detected changes in:', changed)
                # Uruchamiamy restart serwera bezpośrednio po wykryciu zmian
                try:
                    restart_server()
                except Exception as e:
                    print('[dev_watch] Failed to restart server:', e)
                last = cur
    except KeyboardInterrupt:
        print('Watcher stopped')


if __name__ == '__main__':
    main()

