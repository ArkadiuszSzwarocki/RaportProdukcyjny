"""Query service checking GitHub main commits, Actions status, and GHCR image readiness."""

import os
from typing import Any, Dict, List, Optional

import requests

from app.services.app_version_service import get_app_version_info

_DEFAULT_REPO = 'ArkadiuszSzwarocki/RaportProdukcyjny'
_TRACKED_WORKFLOWS = ('Docker Build and Push', 'Test & Build', 'Python tests', 'cSpell')


def _github_headers() -> Dict[str, str]:
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'RaportProdukcyjny-UpdateChecker/1.0',
    }
    token = (os.getenv('GITHUB_TOKEN') or os.getenv('GHCR_TOKEN') or '').strip()
    if token and not token.startswith('CHANGE_THIS'):
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _repo_slug() -> str:
    return (os.getenv('GITHUB_REPOSITORY') or _DEFAULT_REPO).strip()


def _format_iso(value: Optional[str]) -> str:
    if not value:
        return '—'
    return str(value).replace('T', ' ').replace('Z', ' UTC')[:19]


def check_github_image_status() -> Dict[str, Any]:
    """Compare running app version against latest GitHub main commit and CI build status."""
    local_info = get_app_version_info(force_refresh=True)
    local_sha = str(local_info.get('commit_sha') or '').strip().lower()
    repo = _repo_slug()
    headers = _github_headers()

    latest_commit: Dict[str, Any] = {}
    workflows: List[Dict[str, Any]] = []
    docker_build_run: Optional[Dict[str, Any]] = None
    api_error: Optional[str] = None

    with requests.Session() as http:
        try:
            commit_resp = http.get(
                f'https://api.github.com/repos/{repo}/commits/main',
                headers=headers,
                timeout=(4, 8),
            )
            if commit_resp.status_code == 200:
                payload = commit_resp.json()
                full_sha = str(payload.get('sha') or '')
                commit_meta = payload.get('commit') or {}
                author_meta = commit_meta.get('author') or {}
                latest_commit = {
                    'sha': full_sha[:7],
                    'full_sha': full_sha,
                    'date': _format_iso(author_meta.get('date')),
                    'author': author_meta.get('name') or '—',
                    'message': str(commit_meta.get('message') or '').splitlines()[0],
                    'url': payload.get('html_url') or f'https://github.com/{repo}/commits/main',
                }
            elif commit_resp.status_code in (401, 403, 404):
                api_error = (
                    f'GitHub API zwróciło HTTP {commit_resp.status_code}. '
                    'Dla prywatnego repozytorium ustaw zmienną GHCR_TOKEN lub GITHUB_TOKEN w .env.'
                )
            else:
                api_error = f'Nie udało się odczytać commitu z GitHub (HTTP {commit_resp.status_code}).'
        except requests.RequestException as exc:
            api_error = f'Błąd połączenia z GitHub API ({type(exc).__name__}).'

        if not api_error:
            try:
                runs_resp = http.get(
                    f'https://api.github.com/repos/{repo}/actions/runs',
                    params={'branch': 'main', 'per_page': 20},
                    headers=headers,
                    timeout=(4, 8),
                )
                if runs_resp.status_code == 200:
                    seen_names = set()
                    for run in runs_resp.json().get('workflow_runs') or []:
                        wf_name = str(run.get('name') or '')
                        if wf_name not in _TRACKED_WORKFLOWS or wf_name in seen_names:
                            continue
                        seen_names.add(wf_name)
                        entry = {
                            'name': wf_name,
                            'status': run.get('status') or 'unknown',
                            'conclusion': run.get('conclusion') or 'in_progress',
                            'head_sha': str(run.get('head_sha') or '')[:7],
                            'updated_at': _format_iso(run.get('updated_at')),
                            'url': run.get('html_url') or f'https://github.com/{repo}/actions',
                        }
                        workflows.append(entry)
                        if wf_name == 'Docker Build and Push':
                            docker_build_run = entry
            except requests.RequestException:
                pass

    remote_sha = str(latest_commit.get('sha') or '').lower()
    failed_checks = [w['name'] for w in workflows if w['name'] != 'Docker Build and Push' and w['conclusion'] == 'failure']
    docker_ok = bool(docker_build_run and docker_build_run.get('conclusion') == 'success')
    docker_sha = str((docker_build_run or {}).get('head_sha') or '').lower()
    is_same_commit = bool(local_sha and remote_sha and (local_sha.startswith(remote_sha) or remote_sha.startswith(local_sha)))

    if api_error:
        status_code = 'error'
        summary = api_error
    elif docker_ok and docker_sha and local_sha and not (local_sha.startswith(docker_sha) or docker_sha.startswith(local_sha)):
        status_code = 'update_available'
        summary = f'Nowy obraz Docker ({docker_sha}) jest gotowy na GHCR — Watchtower może go pobrać.'
    elif failed_checks:
        status_code = 'ci_blocked'
        summary = (
            'Brak nowego obrazu na GHCR — publikację blokują błędy w GitHub Actions: '
            + ', '.join(failed_checks)
            + '.'
        )
    elif docker_build_run and docker_build_run.get('status') != 'completed':
        status_code = 'building'
        summary = 'Trwa budowanie nowego obrazu Docker w GitHub Actions…'
    elif is_same_commit:
        status_code = 'up_to_date'
        summary = 'Aplikacja działa na najnowszej opublikowanej wersji z gałęzi main.'
    else:
        status_code = 'pending'
        summary = f'Na GitHub jest nowszy commit ({remote_sha}), ale nowy obraz Docker nie został jeszcze opublikowany.'

    return {
        'success': api_error is None,
        'status': status_code,
        'summary': summary,
        'repo': repo,
        'actions_url': f'https://github.com/{repo}/actions',
        'local': {
            'version': local_info.get('version', 'N/A'),
            'commit_sha': local_info.get('commit_sha', '—'),
            'commit_date': local_info.get('commit_date', '—'),
            'diff_size_human': local_info.get('diff_size_human', '0 B'),
        },
        'remote_commit': latest_commit,
        'workflows': workflows,
    }
