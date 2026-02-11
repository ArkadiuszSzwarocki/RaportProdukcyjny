import sys, os
repo_root = os.path.dirname(os.path.dirname(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from app.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, sekcja, produkt, DATE(data_planu), tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE tonaz IS NULL")
rows = cur.fetchall()
if not rows:
    print('No rows with NULL tonaz found.')
else:
    print('Rows with NULL tonaz:')
    for r in rows:
        print(f'ID={r[0]} | sekcja={r[1]} | produkt={r[2]} | data={r[3]} | tonaz={r[4]} | tonaz_rzeczywisty={r[5]}')
cur.close()
conn.close()
