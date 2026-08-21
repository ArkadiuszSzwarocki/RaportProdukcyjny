from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, plan_id, nr_palety, nr_palety_lp, waga, data_dodania FROM palety_workowanie WHERE plan_id=%s ORDER BY id DESC LIMIT 10", (156,))
    rows = cur.fetchall()
    for r in rows:
        print(r)
    cur.close()
    conn.close()

if __name__ == '__main__':
    main()
