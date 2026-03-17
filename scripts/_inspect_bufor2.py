import json
from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    q = '''
    SELECT b.id, b.zasyp_id, b.data_planu, b.produkt, b.tonaz_rzeczywisty, b.spakowano, b.kolejka,
           z.status as zasyp_status, w.status as work_status
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
    LEFT JOIN plan_produkcji w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
    WHERE b.status = 'aktywny'
      AND (COALESCE(z.status,'') != 'zakonczone' OR COALESCE(w.status,'') != 'zakonczone')
    ORDER BY b.data_planu DESC, b.kolejka ASC
    '''
    cur.execute(q)
    rows = cur.fetchall()
    print(json.dumps([list(r) for r in rows], default=str, ensure_ascii=False))
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
