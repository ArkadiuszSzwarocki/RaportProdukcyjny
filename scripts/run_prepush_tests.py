# cspell:words prepush testpass unpushed
"""Pre-push guard running targeted pytest checks for touched modules."""

import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / 'tests'

_STOP_TOKENS = {
    'app', 'services', 'blueprints', 'repositories', 'models', 'core',
    'utils', 'templates', 'static', 'js', 'css', 'html', 'py', 'api',
    'base', 'routes', 'views', 'index', 'modules', 'panels', 'modals',
    'tests', 'test', 'init', 'scripts', 'config', 'docker', 'compose',
    'service', 'repository', 'controller', 'manager', 'helper', 'common',
}

_ALIASES = {
    'factory': {'mqtt', 'security', 'startup', 'instance'},
    'panel': {'plan', 'planista'},
    'planista': {'plan', 'rollover', 'workowanie', 'zasyp'},
    'maluch': {'bucket', 'maluchy'},
    'bucket': {'bucket', 'maluchy'},
    'mqtt': {'mqtt', 'machine', 'telemetry', 'folio'},
    'pallets': {'pallet', 'warehouse', 'stock'},
    'inventory': {'inventory', 'stock', 'packaging'},
}


def _isolated_test_env() -> dict:
    """Build an isolated testing environment so local DB is never touched."""
    env = os.environ.copy()
    env.update({
        'DB_HOST': '127.0.0.1',
        'DB_PORT': '1',
        'DB_CONNECTION_TIMEOUT': '1',
        'DB_USER': 'testuser',
        'DB_PASSWORD': 'testpass',
        'DB_NAME': 'prepush_isolated_db',
        'FLASK_ENV': 'testing',
        'SECRET_KEY': 'ci-test-secret-key',
        'ENCRYPTION_KEY': 'T0Y3M09VNkY2bmt3YXpBS2dCSjVaQlE5cWpsd1JGcVZrbmZ0SEZXVT0=',
        'PRINTER_SERVER_START_PIN': '0606',
        'USE_SSL': 'false',
        'PRINTER_BRIDGE_AUTOSTART': 'false',
        'ENABLE_BACKGROUND_DAEMONS': 'false',
        'ENABLE_MQTT_BRIDGE': 'false',
        'SKIP_DB_SETUP': 'true',
    })
    return env


def _git_changed_files() -> list[str]:
    """Collect files changed in unpushed commits and working tree."""
    files = set()
    commands = [
        ['git', 'diff', '--name-only', 'origin/main..HEAD'],
        ['git', 'diff', '--name-only', 'HEAD'],
    ]
    for cmd in commands:
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                cleaned = line.strip().replace('\\', '/')
                if cleaned:
                    files.add(cleaned)
    return sorted(files)


def _extract_tokens(path_str: str) -> set[str]:
    """Extract meaningful search tokens from a repository file path."""
    tokens = set()
    for part in re.split(r'[^a-zA-Z0-9]+', path_str.lower()):
        if len(part) >= 3 and part not in _STOP_TOKENS:
            tokens.add(part)
            tokens.update(_ALIASES.get(part, ()))
    return tokens


def _find_matching_tests(changed_files: list[str]) -> list[str]:
    """Resolve pytest files relevant to the changed files."""
    if os.getenv('PREPUSH_FULL_PYTEST') == '1':
        return ['tests']

    all_test_files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in TESTS_DIR.rglob('test_*.py')
    )
    selected = set()
    tokens = set()
    for rel_path in changed_files:
        if rel_path.startswith('tests/') and Path(rel_path).name.startswith('test_') and rel_path.endswith('.py'):
            if (ROOT / rel_path).is_file():
                selected.add(rel_path)
            continue
        if rel_path.endswith(('.py', '.html', '.js')):
            tokens.update(_extract_tokens(rel_path))

    if tokens:
        for test_path in all_test_files:
            test_name = Path(test_path).stem.lower()
            if any(tok in test_name for tok in tokens):
                selected.add(test_path)

    return sorted(selected)


def main() -> int:
    """Run matched unit tests and propagate pytest exit status."""
    probe = subprocess.run(
        [sys.executable, '-m', 'pytest', '--version'],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        print('[pre-push] pytest not installed; skipping unit tests.')
        return 0

    changed_files = _git_changed_files()
    test_targets = _find_matching_tests(changed_files)
    if not test_targets:
        print('[pre-push] No matching unit test files for changed paths.')
        return 0

    print(f"[pre-push] Running targeted pytest ({len(test_targets)} target(s))...")
    env = _isolated_test_env()
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-q', *test_targets],
        cwd=ROOT,
        env=env,
        check=False,
    )
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
