"""Read-only service providing application version and latest update metadata."""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

_CACHE_TTL_SECONDS = 30.0
_cached_payload: Optional[Dict[str, Any]] = None
_cached_at: float = 0.0
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def format_bytes(size_bytes: int) -> str:
    """Format a byte count into a human-readable Polish/SI unit string."""
    size = max(0, int(size_bytes or 0))
    if size < 1024:
        return f'{size} B'
    if size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    return f'{size / (1024 * 1024):.2f} MB'


def extract_semver(raw_version: str) -> str:
    """Extract MAJOR.MINOR.PATCH from VERSION text, or fall back to raw string."""
    text = str(raw_version or '').strip()
    match = re.search(r'\b(\d+\.\d+\.\d+)\b', text)
    return match.group(1) if match else (text or '0.0.0')


def _read_version_file() -> str:
    version_path = _PROJECT_ROOT / 'VERSION'
    try:
        return version_path.read_text(encoding='utf-8').strip()
    except OSError:
        return 'N/A'


def _read_version_info_json() -> Dict[str, Any]:
    info_path = _PROJECT_ROOT / 'version_info.json'
    if not info_path.is_file():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _run_git(args) -> Optional[str]:
    try:
        result = subprocess.run(
            ['git', *args],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _read_git_head_metadata() -> Dict[str, Any]:
    """Fallback metadata from local git repository when running outside Docker."""
    log_raw = _run_git(['log', '-1', '--format=%h|%ad|%an|%s', '--date=format:%Y-%m-%d %H:%M'])
    if not log_raw or '|' not in log_raw:
        return {}
    parts = log_raw.strip().split('|', 3)
    if len(parts) < 4:
        return {}

    sha, commit_date, author, message = parts
    files_changed = 0
    insertions = 0
    deletions = 0
    numstat = _run_git(['diff-tree', '--no-commit-id', '--numstat', '-r', '--root', 'HEAD']) or ''
    for line in numstat.splitlines():
        cols = line.split('\t')
        if len(cols) >= 3:
            files_changed += 1
            if cols[0].isdigit():
                insertions += int(cols[0])
            if cols[1].isdigit():
                deletions += int(cols[1])

    patch = _run_git(['diff-tree', '--no-commit-id', '-p', '--root', 'HEAD']) or ''
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


def get_app_version_info(force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached application version and latest update details."""
    global _cached_payload, _cached_at
    now = time.monotonic()
    if not force_refresh and _cached_payload is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return dict(_cached_payload)

    raw_version = _read_version_file()
    semver = extract_semver(raw_version)
    info = _read_version_info_json()

    if not info.get('commit_sha') or not info.get('commit_date'):
        git_meta = _read_git_head_metadata()
        for key, value in git_meta.items():
            if not info.get(key):
                info[key] = value

    diff_bytes = int(info.get('diff_size_bytes') or 0)
    payload = {
        'version': extract_semver(info.get('version') or semver),
        'version_raw': raw_version,
        'commit_sha': str(info.get('commit_sha') or '—'),
        'commit_date': str(info.get('commit_date') or '—'),
        'commit_message': str(info.get('commit_message') or 'Brak opisu aktualizacji'),
        'author': str(info.get('author') or '—'),
        'files_changed': int(info.get('files_changed') or 0),
        'insertions': int(info.get('insertions') or 0),
        'deletions': int(info.get('deletions') or 0),
        'diff_size_bytes': diff_bytes,
        'diff_size_human': format_bytes(diff_bytes),
    }

    _cached_payload = payload
    _cached_at = now
    return dict(payload)
