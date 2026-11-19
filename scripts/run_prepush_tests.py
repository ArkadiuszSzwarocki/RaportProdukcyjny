# cspell:words prepush testpass unpushed
"""Pre-push guard running targeted pytest checks for touched modules."""

import ast
import importlib.util
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
    'factory': {'mqtt', 'startup'},
    'maluch': {'bucket', 'maluchy'},
    'bucket': {'bucket', 'maluchy'},
    'mqtt': {'mqtt', 'machine', 'telemetry'},
}

_MAX_TEST_TARGETS = 5


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
    """Extract meaningful search tokens from an application module path."""
    tokens = set()
    for part in re.split(r'[^a-zA-Z0-9]+', path_str.lower()):
        if len(part) >= 3 and part not in _STOP_TOKENS:
            tokens.add(part)
            tokens.update(_ALIASES.get(part, ()))
    return tokens


def _has_available_imports(test_file: Path) -> bool:
    """Return True if all third-party top-level imports in test_file are installed."""
    try:
        tree = ast.parse(test_file.read_text(encoding='utf-8'))
    except Exception:
        return True
    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.Import):
            module_name = node.names[0].name.split('.')[0] if node.names else None
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            module_name = node.module.split('.')[0]
        if not module_name or module_name in sys.stdlib_module_names or module_name in ('app', 'printer_server', 'scripts', 'tests'):
            continue
        if importlib.util.find_spec(module_name) is None:
            return False
    return True


def _find_matching_tests(changed_files: list[str]) -> list[str]:
    """Resolve the top pytest files directly relevant to changed app code."""
    if os.getenv('PREPUSH_FULL_PYTEST') == '1':
        return ['tests']

    all_test_files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in TESTS_DIR.rglob('test_*.py')
    )
    direct_tests = set()
    tokens = set()
    for rel_path in changed_files:
        if rel_path.startswith('tests/') and Path(rel_path).name.startswith('test_') and rel_path.endswith('.py'):
            candidate = ROOT / rel_path
            if candidate.is_file() and _has_available_imports(candidate):
                direct_tests.add(rel_path)
            continue
        if rel_path.startswith(('app/', 'printer_server/')) and rel_path.endswith('.py'):
            tokens.update(_extract_tokens(rel_path))

    scored = []
    if tokens:
        for test_path in all_test_files:
            if test_path in direct_tests:
                continue
            full_path = ROOT / test_path
            if not _has_available_imports(full_path):
                continue
            test_name = Path(test_path).stem.lower()
            hits = sum(len(tok) for tok in tokens if tok in test_name)
            if hits > 0:
                scored.append((hits, test_path))

    scored.sort(key=lambda item: (-item[0], item[1]))
    picked = [path for _, path in scored[:max(0, _MAX_TEST_TARGETS - len(direct_tests))]]
    return sorted(direct_tests.union(picked))


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
