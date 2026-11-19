"""Bump SemVer PATCH in VERSION and generate version_info.json on commit/push."""

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = PROJECT_ROOT / 'VERSION'
VERSION_INFO_FILE = PROJECT_ROOT / 'version_info.json'


def _run_git(args) -> Optional[str]:
    try:
        result = subprocess.run(
            ['git', *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _parse_semver(text: str):
    match = re.search(r'\b(\d+)\.(\d+)\.(\d+)\b', str(text or ''))
    if not match:
        return 2, 2, 0
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _read_current_version() -> str:
    if not VERSION_FILE.is_file():
        return '2.2.0'
    major, minor, patch = _parse_semver(VERSION_FILE.read_text(encoding='utf-8'))
    return f'{major}.{minor}.{patch}'


def _bump_patch_version(version_str: str) -> str:
    major, minor, patch = _parse_semver(version_str)
    return f'{major}.{minor}.{patch + 1}'


def _collect_staged_stats() -> Dict[str, Any]:
    numstat = _run_git(['diff', '--cached', '--numstat']) or ''
    files_changed = 0
    insertions = 0
    deletions = 0
    for line in numstat.splitlines():
        cols = line.split('\t')
        if len(cols) >= 3:
            path = cols[2].strip()
            if path in ('VERSION', 'version_info.json'):
                continue
            files_changed += 1
            if cols[0].isdigit():
                insertions += int(cols[0])
            if cols[1].isdigit():
                deletions += int(cols[1])

    patch = _run_git(['diff', '--cached', '--', '.', ':!VERSION', ':!version_info.json']) or ''
    diff_bytes = len(patch.encode('utf-8'))
    author = (_run_git(['config', 'user.name']) or '').strip() or 'Developer'
    head_sha = (_run_git(['rev-parse', '--short', 'HEAD']) or '').strip() or 'local'

    return {
        'commit_sha': head_sha,
        'commit_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'author': author,
        'commit_message': 'Aktualizacja aplikacji',
        'files_changed': files_changed,
        'insertions': insertions,
        'deletions': deletions,
        'diff_size_bytes': diff_bytes,
    }


def _collect_head_stats() -> Dict[str, Any]:
    log_raw = _run_git(['log', '-1', '--format=%h|%ad|%an|%s', '--date=format:%Y-%m-%d %H:%M']) or ''
    parts = log_raw.strip().split('|', 3)
    if len(parts) == 4:
        sha, commit_date, author, message = parts
    else:
        sha, commit_date, author, message = '—', datetime.now().strftime('%Y-%m-%d %H:%M'), '—', 'Aktualizacja aplikacji'

    numstat = _run_git(['diff-tree', '--no-commit-id', '--numstat', '-r', '--root', 'HEAD']) or ''
    files_changed = 0
    insertions = 0
    deletions = 0
    for line in numstat.splitlines():
        cols = line.split('\t')
        if len(cols) >= 3:
            path = cols[2].strip()
            if path in ('VERSION', 'version_info.json'):
                continue
            files_changed += 1
            if cols[0].isdigit():
                insertions += int(cols[0])
            if cols[1].isdigit():
                deletions += int(cols[1])

    patch = _run_git(['diff-tree', '--no-commit-id', '-p', '--root', 'HEAD', '--', '.', ':!VERSION', ':!version_info.json']) or ''
    diff_bytes = len(patch.encode('utf-8'))

    return {
        'commit_sha': sha,
        'commit_date': commit_date,
        'author': author,
        'commit_message': message,
        'files_changed': files_changed,
        'insertions': insertions,
        'deletions': deletions,
        'diff_size_bytes': diff_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Update VERSION and version_info.json')
    parser.add_argument('--bump', action='store_true', help='Increment PATCH version in VERSION')
    parser.add_argument('--staged', action='store_true', help='Measure staged changes (for pre-commit hook)')
    parser.add_argument('--refresh', action='store_true', help='Refresh version_info.json from HEAD without bumping')
    args = parser.parse_args()

    current = _read_current_version()
    target_version = _bump_patch_version(current) if args.bump else current
    stats = _collect_staged_stats() if args.staged else _collect_head_stats()

    today_str = datetime.now().strftime('%Y-%m-%d')
    if args.bump or not VERSION_FILE.is_file():
        VERSION_FILE.write_text(f'{target_version} ({today_str})\n', encoding='utf-8')

    payload = {
        'version': target_version,
        **stats,
    }
    VERSION_INFO_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'[version] {target_version} (files={stats["files_changed"]}, bytes={stats["diff_size_bytes"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
