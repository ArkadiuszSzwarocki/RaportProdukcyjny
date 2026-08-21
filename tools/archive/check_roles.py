#!/usr/bin/env python3
"""Quick diagnostic: list users with missing or empty `rola`.

Run locally: `python tools/check_roles.py`
"""
import os
import sys

# Ensure project root is on sys.path so `import app` works when running this script
# directly (sys.path[0] is tools/ when invoked as `python tools/check_roles.py`).
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.db import get_db_connection


def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, login, COALESCE(rola, '') FROM uzytkownicy ORDER BY id")
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    no_role = [r for r in rows if not (r[2] and str(r[2]).strip())]
    by_role = {}
    for r in rows:
        role = (r[2] or '').strip()
        by_role[role] = by_role.get(role, 0) + 1

    print(f"Total users: {total}")
    print(f"Users with no role: {len(no_role)}")
    if no_role:
        print("- List of users without role:")
        for r in no_role:
            print(f"  id={r[0]} login={r[1]!r}")

    print("\nRole distribution:")
    for role, cnt in sorted(by_role.items(), key=lambda x: (x[0] != '', -x[1])):
        disp = role if role else '<EMPTY>'
        print(f"  {disp}: {cnt}")


if __name__ == '__main__':
    main()
