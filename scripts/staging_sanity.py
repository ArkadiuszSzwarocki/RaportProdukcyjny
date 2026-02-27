#!/usr/bin/env python3
"""Simple sanity checks to run against staging after migration.

Usage:
  export STAGING_URL=https://staging.example.com
  python scripts/staging_sanity.py

The script performs basic HTTP checks (GET / and queue endpoint) and reports status.
"""
import os
import sys
import requests

BASE = os.environ.get('STAGING_URL')
if not BASE:
    print('Set STAGING_URL environment variable, e.g. https://staging.example.com')
    sys.exit(2)

TIMEOUT = 10

def check_root():
    url = BASE.rstrip('/') + '/'
    print('Checking root:', url)
    r = requests.get(url, timeout=TIMEOUT)
    print('Status:', r.status_code)
    return r.status_code == 200

def check_plan_queue():
    url = BASE.rstrip('/') + '/api/planista/queue?sekcja=Workowanie'
    print('Checking plan queue:', url)
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except Exception as e:
        print('Request failed:', str(e))
        return False
    print('Status:', r.status_code)
    return r.status_code == 200

if __name__ == '__main__':
    ok = True
    if not check_root():
        ok = False
    if not check_plan_queue():
        ok = False

    if ok:
        print('Sanity checks passed.')
        sys.exit(0)
    else:
        print('Sanity checks failed.')
        sys.exit(1)
