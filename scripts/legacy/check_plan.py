import os
import sys

# Ensure repo root is on sys.path so `import db` works when running from scripts/
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from db import get_db_connection


def check(plan_id=367):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE id=%s", (plan_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        print(f"No plan with id={plan_id}")
        return
    for r in rows:
        print(r)


if __name__ == '__main__':
    check()
