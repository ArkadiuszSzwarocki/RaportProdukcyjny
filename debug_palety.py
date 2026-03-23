import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from app.db import get_db_connection

def run():
    conn = get_db_connection()
    c = conn.cursor(dictionary=True)
    c.execute('SELECT id, plan_id, paleta_workowanie_id, waga_netto, produkt FROM magazyn_palety ORDER BY id DESC LIMIT 5')
    print("--- MAGAZYN ---")
    for r in c.fetchall(): print(r)
    c.execute('SELECT id, plan_id, waga FROM palety_workowanie ORDER BY id DESC LIMIT 5')
    print("--- WORKOWANIE ---")
    for r in c.fetchall(): print(r)
    conn.close()

if __name__ == '__main__':
    run()
