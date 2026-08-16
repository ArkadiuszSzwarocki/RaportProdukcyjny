"""Count ROUTE_TEST_PROD rows in DB."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM plan_produkcji WHERE produkt = %s", ('ROUTE_TEST_PROD',))
    print(cur.fetchone()[0])
    conn.close()

if __name__ == '__main__':
    main()
