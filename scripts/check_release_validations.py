"""Publish images only after all validation workflows pass on the same commit."""
import json
import os
import re
import subprocess
import sys

REQUIRED = {'Test & Build', 'Python tests', 'cSpell'}


def publication_ready(runs, sha):
    latest = {}
    for run in runs:
        if (run.get('head_sha') != sha or run.get('head_branch') != 'main'
                or run.get('event') != 'push' or run.get('name') not in REQUIRED):
            continue
        name = run['name']
        if name not in latest or (run['id'], run.get('run_attempt', 1)) > (latest[name]['id'], latest[name].get('run_attempt', 1)):
            latest[name] = run
    return all(name in latest and latest[name].get('status') == 'completed'
               and latest[name].get('conclusion') == 'success' for name in REQUIRED)


def main():
    sha = sys.argv[1]
    repo = os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid release identity')
    result = subprocess.run(['gh', 'api', '--method', 'GET', f'repos/{repo}/actions/runs',
                             '-f', f'head_sha={sha}', '-f', 'event=push', '-f', 'per_page=100'],
                            check=True, capture_output=True, text=True, timeout=30)
    ready = publication_ready(json.loads(result.stdout)['workflow_runs'], sha)
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('ready=' + str(ready).lower() + '\n')
    print('All release validations passed: ' + str(ready))


if __name__ == '__main__':
    main()
