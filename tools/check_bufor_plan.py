import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db_connection
import requests
import os


def check(plan_id=315, base='http://localhost:8082'):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, data_planu, produkt, tonaz_rzeczywisty, nazwa_zlecenia, typ_produkcji FROM plan_produkcji WHERE id=%s", (plan_id,))
        row = cur.fetchone()
        if not row:
            print(f'NO PLAN id={plan_id}')
            return 2
        print('PLAN:', row)
        h_id, h_data, h_produkt, h_wykonanie_zasyp, h_nazwa, h_typ = row
        typ_param = h_typ if h_typ is not None else ''
        cur.execute(
            "SELECT SUM(waga) FROM palety_workowanie WHERE plan_id = %s OR plan_id IN (SELECT id FROM plan_produkcji WHERE data_planu=%s AND produkt=%s AND sekcja='Workowanie' AND COALESCE(typ_produkcji,'')=%s)",
            (h_id, h_data, h_produkt, typ_param)
        )
        res_pal = cur.fetchone()
        h_wykonanie_workowanie = res_pal[0] if res_pal and res_pal[0] else 0
        pozostalo_w_silosie = (h_wykonanie_zasyp or 0) - (h_wykonanie_workowanie or 0)
        print('SUM_PALET_WORKOWANIE:', h_wykonanie_workowanie)
        print('TONAZ_RZECZYWISTY (zasyp):', h_wykonanie_zasyp)
        print('POZOSTALO_W_SILOSIE:', pozostalo_w_silosie)
    except Exception as e:
        print('DB ERROR', e)
        return 3
    finally:
        try:
            conn.close()
        except Exception:
            pass

    try:
        session = requests.Session()
        r = session.get(base + '/bufor', timeout=10)
        # If server returned login page, try to authenticate using env TEST_LOGIN/TEST_PASSWORD
        if 'Zaloguj' in r.text or '<form method="POST">' in r.text:
            test_login = os.environ.get('TEST_LOGIN')
            test_pass = os.environ.get('TEST_PASSWORD')
            if test_login and test_pass:
                login_resp = session.post(base + '/login', data={'login': test_login, 'haslo': test_pass}, timeout=10)
                # try fetching bufor again
                r = session.get(base + '/bufor', timeout=10)

        with open('tools/last_bufor_response.html', 'w', encoding='utf-8') as fh:
            fh.write(r.text)
        found = str(plan_id) in r.text
        print('BUFOR HTTP STATUS', r.status_code, 'plan_id_present_in_html=', found)
    except Exception as e:
        print('HTTP ERROR', e)
        return 4

    return 0

if __name__ == '__main__':
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 315
    sys.exit(check(pid))
