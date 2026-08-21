#!/usr/bin/env python3
from app.db import get_db_connection
import json

def run_query(sql, params=None):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        print(f"-- {sql} params={params} -> {len(rows)} rows")
        for r in rows:
            # format datetime/date
            out = []
            for v in r:
                try:
                    if hasattr(v, 'strftime'):
                        out.append(v.strftime('%Y-%m-%d %H:%M:%S'))
                    else:
                        out.append(v)
                except Exception:
                    out.append(str(v))
            print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print('ERROR:', e)
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    date_str = '2026-03-17'

    q1 = "SELECT id, sekcja, typ_zlecenia, data_planu, status, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE DATE(data_planu) = %s ORDER BY id"
    run_query(q1, (date_str,))

    q2 = "SELECT id, sekcja, typ_zlecenia, data_planu, status, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu = %s ORDER BY id"
    run_query(q2, (date_str + ' 00:00:00',))

    q3 = "SELECT id, sekcja, typ_zlecenia, data_planu, status, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE DATE(data_planu) = %s AND LOWER(sekcja) = 'workowanie' ORDER BY id"
    run_query(q3, (date_str,))

    q4 = "SELECT id, sekcja, typ_zlecenia, data_planu, status, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE DATE(data_planu) = %s AND COALESCE(typ_zlecenia, '') = 'carry_over_ghost' ORDER BY id"
    run_query(q4, (date_str,))
