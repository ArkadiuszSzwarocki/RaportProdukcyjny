import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection


def set_val(plan_id, value):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE plan_produkcji SET tonaz_rzeczywisty=%s WHERE id=%s", (value, plan_id))
        conn.commit()
        print(f'UPDATED plan_id={plan_id} tonaz_rzeczywisty={value}')
        return 0
    except Exception as e:
        print('ERROR', e)
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 315
    val = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    sys.exit(set_val(pid, val))
