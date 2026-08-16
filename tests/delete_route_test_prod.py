import os
import sys
# Ensure repo root is on sys.path when running the script directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.db import get_db_connection

def delete_test_orders():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM plan_produkcji WHERE produkt = %s", ('ROUTE_TEST_PROD',))
        before = cur.fetchone()[0]
        if before == 0:
            print('[delete_route_test_prod] No ROUTE_TEST_PROD rows found')
            return
        cur.execute("DELETE FROM plan_produkcji WHERE produkt = %s", ('ROUTE_TEST_PROD',))
        deleted = cur.rowcount
        conn.commit()
        print(f"[delete_route_test_prod] Deleted {deleted} rows (found {before})")
    except Exception as e:
        print(f"[delete_route_test_prod] ERROR: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()

if __name__ == '__main__':
    delete_test_orders()
