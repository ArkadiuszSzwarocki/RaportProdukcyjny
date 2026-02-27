import threading
import time
from datetime import date

from app.db import get_db_connection


def worker_post_create(client_app, zasyp_id, results, idx):
    client = client_app.test_client()
    # authenticate this client as 'lider' to have permissions
    with client.session_transaction() as sess:
        sess['user_id'] = 10
        sess['username'] = f'thread-{idx}'
        sess['rola'] = 'lider'
        sess['zalogowany'] = True

    resp = client.post('/bufor/create_zlecenie', data={'zasyp_id': str(zasyp_id)})
    results[idx] = (resp.status_code, resp.get_json() if resp.is_json else resp.data.decode('utf-8'))


def test_concurrent_create_workowanie_route(app):
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    zasyp_id = None
    try:
        # insert a Zasyp plan
        cur.execute(
            "INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (today, 'Zasyp', 'ROUTE_TEST_PROD', 200.0, 200.0, 'worki_zgrzewane_25', 'ROUTETEST', 'w toku')
        )
        zasyp_id = cur.lastrowid
        conn.commit()

        # ensure no existing Workowanie for this zasyp_id
        cur.execute("DELETE FROM plan_produkcji WHERE sekcja='Workowanie' AND zasyp_id=%s", (zasyp_id,))
        conn.commit()

        threads = []
        results = [None] * 6
        for i in range(6):
            t = threading.Thread(target=worker_post_create, args=(app, zasyp_id, results, i))
            threads.append(t)

        for t in threads:
            t.start()
            time.sleep(0.01)

        for t in threads:
            t.join()

        # verify exactly one Workowanie created for this zasyp
        cur.execute("SELECT COUNT(*) FROM plan_produkcji WHERE sekcja='Workowanie' AND zasyp_id=%s", (zasyp_id,))
        cnt = cur.fetchone()[0]
        assert cnt == 1, f"Expected 1 Workowanie for zasyp_id={zasyp_id}, found {cnt}, results={results}"

    finally:
        try:
            if zasyp_id:
                cur.execute("DELETE FROM plan_produkcji WHERE zasyp_id=%s", (zasyp_id,))
                conn.commit()
        except Exception:
            pass
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
