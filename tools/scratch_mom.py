import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor(dictionary=True)

code = 'AGR000001779899912233'
print("Checking tables for code...")

# Let's search all tables
cur.execute("SHOW TABLES")
tables = [list(r.values())[0] for r in cur.fetchall()]
for t in tables:
    try:
        cur.execute(f"SELECT * FROM {t} LIMIT 1")
        row = cur.fetchone()
        if not row:
            continue
        cols = list(row.keys())
        match_cols = [c for c in cols if 'palet' in c.lower() or 'nazwa' in c.lower() or 'produkt' in c.lower() or 'id' in c.lower()]
        if match_cols:
            query = f"SELECT * FROM {t} WHERE " + " OR ".join([f"CAST({c} AS CHAR) = %s" for c in match_cols])
            cur.execute(query, tuple([code] * len(match_cols)))
            res = cur.fetchall()
            if res:
                print(f"Match in table {t}:")
                for r in res:
                    print(f"  {r}")
    except Exception as e:
        pass

conn.close()
