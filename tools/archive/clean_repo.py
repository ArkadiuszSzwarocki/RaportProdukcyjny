#!/usr/bin/env python3
"""Repo cleanup helper.

Scans for likely temporary/generated files and offers to delete them.

Default targets:
- backups/*.zip
- raporty_temp/*
- raporty/*.pdf (older than --days)
- panel_obsada_response.html (root)

Usage:
  python tools/clean_repo.py        # interactive prompt
  python tools/clean_repo.py --yes # delete without prompt
  python tools/clean_repo.py --days 3
"""
import argparse
import glob
import os
import time
from pathlib import Path


def find_candidates(root, days):
    now = time.time()
    candidates = []
    # backups zip
    for p in glob.glob(os.path.join(root, 'backups', '*.zip')):
        candidates.append(p)
    # raporty_temp
    for p in glob.glob(os.path.join(root, 'raporty_temp', '*')):
        candidates.append(p)
    # raporty pdf older than days
    for p in glob.glob(os.path.join(root, 'raporty', '*.pdf')):
        try:
            m = os.path.getmtime(p)
        except Exception:
            m = now
        if (now - m) > days * 86400:
            candidates.append(p)
    # panel response file
    panel = os.path.join(root, 'panel_obsada_response.html')
    if os.path.exists(panel):
        candidates.append(panel)
    return sorted(set(candidates))


def human_size(path):
    try:
        s = os.path.getsize(path)
    except Exception:
        return 'n/a'
    for unit in ['B','KB','MB','GB']:
        if s < 1024:
            return f"{s:.0f}{unit}"
        s /= 1024.0
    return f"{s:.1f}TB"


def parse_args():
    p = argparse.ArgumentParser(description='Clean repo generated files')
    p.add_argument('--days', type=int, default=7, help='Age threshold (days) for raporty/*.pdf')
    p.add_argument('--yes', action='store_true', help='Delete without confirmation')
    return p.parse_args()


def main():
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    cand = find_candidates(str(root), args.days)
    if not cand:
        print('No candidates found for cleanup.')
        return
    total = 0
    print('Found the following files:')
    for f in cand:
        try:
            sz = human_size(f)
        except Exception:
            sz = 'n/a'
        print(f'- {f} ({sz})')
        try:
            total += os.path.getsize(f)
        except Exception:
            pass
    print(f'Total size: {human_size_temp(total)}')
    if not args.yes:
        ok = input('Delete these files? (tak/no): ').strip().lower()
        if ok not in ('tak','y','yes'):
            print('Aborted.')
            return
    # perform deletion
    removed = 0
    for f in cand:
        try:
            if os.path.isdir(f):
                # remove directory contents
                for root_dir, dirs, files in os.walk(f, topdown=False):
                    for name in files:
                        fp = os.path.join(root_dir, name)
                        try:
                            os.remove(fp)
                            removed += 1
                        except Exception:
                            pass
                    for name in dirs:
                        dp = os.path.join(root_dir, name)
                        try:
                            os.rmdir(dp)
                        except Exception:
                            pass
                try:
                    os.rmdir(f)
                except Exception:
                    pass
            else:
                os.remove(f)
                removed += 1
        except Exception as e:
            print('Failed to remove', f, e)
    print(f'Done. Removed ~{removed} items.')


def human_size_temp(n):
    s = float(n)
    for unit in ['B','KB','MB','GB']:
        if s < 1024:
            return f"{s:.0f}{unit}"
        s /= 1024.0
    return f"{s:.1f}TB"


if __name__ == '__main__':
    main()
