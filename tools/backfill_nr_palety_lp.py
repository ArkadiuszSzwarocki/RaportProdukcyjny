from app.db import get_db_connection

def backfill():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT DISTINCT plan_id FROM palety_workowanie WHERE plan_id IS NOT NULL')
        plans = [r[0] for r in cur.fetchall()]
        for p in plans:
            cur.execute('SELECT id FROM palety_workowanie WHERE plan_id=%s ORDER BY id ASC', (p,))
            rows = cur.fetchall()
            for idx, row in enumerate(rows, start=1):
                pid = row[0]
                cur.execute('UPDATE palety_workowanie SET nr_palety_lp=%s WHERE id=%s', (idx, pid))
        conn.commit()
        print('Backfill completed for plans:', len(plans))
    except Exception as e:
        print('Error during backfill', e)
    finally:
        cur.close(); conn.close()

if __name__ == '__main__':
    backfill()
