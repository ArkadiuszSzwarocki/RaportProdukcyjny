#!/usr/bin/env python
import sys, json, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

def fetch(sql):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(sql)
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows

names = set()
queries = [
    "SELECT DISTINCT nazwa FROM magazyn_agro_surowce WHERE nazwa IS NOT NULL",
    "SELECT DISTINCT nazwa FROM magazyn_agro_slownik_surowce WHERE nazwa IS NOT NULL"
]
for q in queries:
    try:
        for n in fetch(q):
            if n:
                names.add(n)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)

out = sorted(names)
for n in out:
    print(n)

print('JSON_OUTPUT_START')
print(json.dumps(out, ensure_ascii=False))
print('JSON_OUTPUT_END')
