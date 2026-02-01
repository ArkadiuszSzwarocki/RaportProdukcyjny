import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db
from datetime import date

def main():
    conn = db.get_db_connection()
    cur = conn.cursor()
    d = str(date.today())
    cur.execute("SELECT id, produkt, sekcja, tonaz, status FROM plan_produkcji WHERE data_planu=%s", (d,))
    rows = cur.fetchall()
    print('Plans for', d, 'count=', len(rows))
    for r in rows:
        print(r)
    conn.close()

if __name__ == '__main__':
    main()
