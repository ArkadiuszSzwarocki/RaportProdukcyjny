import sys
import os
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pw.id, pw.plan_id, pw.waga, COALESCE(p.produkt, ''), pw.data_dodania, pw.data_potwierdzenia, pw.czas_potwierdzenia_s, COALESCE(pw.status,'') FROM palety_workowanie pw LEFT JOIN plan_produkcji p ON pw.plan_id = p.id WHERE pw.id IN (184,185)")
    rows = cursor.fetchall()
    for r in rows:
        print(r)
    conn.close()

if __name__ == '__main__':
    main()
