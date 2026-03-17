import json
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    q = '''
    SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.tonaz_rzeczywisty, b.spakowano, b.kolejka, p.status
    FROM bufor b
    LEFT JOIN plan_produkcji p ON p.id = b.zasyp_id
    WHERE b.status = 'aktywny' AND (COALESCE(b.tonaz_rzeczywisty,0) - COALESCE(b.spakowano,0)) > 0
    ORDER BY b.data_planu DESC, b.kolejka ASC
    '''
    cur.execute(q)
    rows = cur.fetchall()
    print(json.dumps([list(r) for r in rows], default=str, ensure_ascii=False))
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
