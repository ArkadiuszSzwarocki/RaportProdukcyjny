import sys
import os
# ensure repo root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection

def check(paleta_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, plan_id, waga, tara, waga_brutto, data_dodania, COALESCE(status,'') FROM palety_workowanie WHERE id=%s", (paleta_id,))
        row = cur.fetchone()
        if not row:
            print(f'NOT FOUND paleta id={paleta_id}')
            return 2
        print('PALLETA:', row)
        # Also show plan summary
        cur.execute("SELECT id, sekcja, produkt, tonaz, tonaz_rzeczywisty, status FROM plan_produkcji WHERE id=%s", (row[1],))
        plan = cur.fetchone()
        print('PLAN:', plan)
        return 0
    except Exception as e:
        print('ERROR', e)
        return 3
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 499
    sys.exit(check(pid))
