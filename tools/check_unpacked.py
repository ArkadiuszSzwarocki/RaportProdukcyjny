#!/usr/bin/env python3
import os
import sys

# Ensure project root is on sys.path so `import app` works when script is run directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.db import get_db_connection


def main():
    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
    SELECT w.id, DATE(w.data_planu) as data_planu, w.produkt, w.nazwa_zlecenia,
           COALESCE(w.tonaz,0) as tonaz_plan,
           COALESCE(w.tonaz_rzeczywisty,0) as tonaz_rz,
           COALESCE((
               SELECT COALESCE(SUM(pw.waga),0) FROM palety_workowanie pw WHERE pw.plan_id = w.id
           ),0) as spakowano
    FROM plan_produkcji w
    WHERE LOWER(w.sekcja) = 'workowanie'
    HAVING tonaz_plan > spakowano
    ORDER BY data_planu DESC, w.id ASC
    """

    try:
        cur.execute(sql)
        rows = cur.fetchall()

        if not rows:
            print("Brak zleceń Workowanie z niedoborem spakowanego towaru.")
            return

        print("Zlecenia Workowanie z niedoborem (plan > spakowano):")
        print("ID\tData\tProdukt\tNazwa\tPlan(kg)\tSpakowano(kg)\tPozostalo(kg)")
        for r in rows:
            # row format: (id, data_planu, produkt, nazwa_zlecenia, tonaz_plan, tonaz_rz, spakowano)
            pid = r[0]
            data = r[1]
            produkt = r[2]
            nazwa = (r[3] or '').replace('\n', ' ')
            plan = float(r[4] or 0)
            spakowano = float(r[6] or 0)
            pozostalo = plan - spakowano
            print(f"{pid}\t{data}\t{produkt}\t{nazwa}\t{plan:.1f}\t{spakowano:.1f}\t{pozostalo:.1f}")

    except Exception as e:
        print(f"Błąd podczas zapytania: {e}")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()
