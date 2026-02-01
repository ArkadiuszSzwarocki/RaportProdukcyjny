import sys, os
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from db import get_db_connection

def main(plan_id=367):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COALESCE(SUM(waga),0) FROM palety_workowanie WHERE plan_id=%s", (plan_id,))
    print('count,total', cur.fetchone())
    cur.execute("SELECT id, waga, status, data_dodania FROM palety_workowanie WHERE plan_id=%s ORDER BY id DESC LIMIT 10", (plan_id,))
    rows = cur.fetchall()
    for r in rows:
        print(r)
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
