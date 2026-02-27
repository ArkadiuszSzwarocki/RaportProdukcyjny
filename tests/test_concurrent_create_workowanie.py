import threading
import time
from app.db import get_db_connection
from datetime import date


def insert_workowanie_atomic(zasyp_id, z_data, produkt, z_typ, z_nazwa, roznicza, results, idx):
    """Worker: try to insert Workowanie using the same atomic SQL as the route."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        insert_sql = """
            INSERT INTO plan_produkcji
            (data_planu, sekcja, produkt, tonaz, status, kolejnosc, typ_produkcji, nazwa_zlecenia, zasyp_id)
            SELECT %s, 'Workowanie', %s, %s, 'zaplanowane', %s, %s, %s, %s
            FROM DUAL
            WHERE NOT EXISTS (SELECT 1 FROM plan_produkcji WHERE zasyp_id = %s AND sekcja = 'Workowanie')
        """
        params = (z_data, produkt, round(roznicza, 1), 1, z_typ, (z_nazwa or '') + '_BUF', zasyp_id, zasyp_id)
        cur.execute(insert_sql, params)
        conn.commit()
        results[idx] = ('ok', cur.rowcount)
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        results[idx] = ('err', str(e))
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()


def test_concurrent_create_workowanie():
    conn = get_db_connection()
    cur = conn.cursor()
    # Prepare a Zasyp plan
    today = date.today()
    try:
        cur.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, tonaz_rzeczywisty, typ_produkcji, nazwa_zlecenia, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (today, 'Zasyp', 'TEST_PROD', 100.0, 100.0, 'worki_zgrzewane_25', 'TESTBUF', 'w toku'))
        zasyp_id = cur.lastrowid
        conn.commit()

        # Ensure no existing Workowanie
        cur.execute("DELETE FROM plan_produkcji WHERE sekcja='Workowanie' AND zasyp_id=%s", (zasyp_id,))
        conn.commit()

        threads = []
        results = [None] * 5
        for i in range(5):
            t = threading.Thread(target=insert_workowanie_atomic, args=(zasyp_id, today, 'TEST_PROD', 'worki_zgrzewane_25', 'TESTBUF', 50.0, results, i))
            threads.append(t)

        # Start threads with tiny stagger to increase contention
        for t in threads:
            t.start()
            time.sleep(0.02)

        for t in threads:
            t.join()

        # Check results: at most one successful insert (rowcount==1)
        cur.execute("SELECT COUNT(*) FROM plan_produkcji WHERE sekcja='Workowanie' AND zasyp_id=%s", (zasyp_id,))
        cnt = cur.fetchone()[0]
        assert cnt == 1, f"Expected exactly 1 Workowanie for zasyp_id={zasyp_id}, found {cnt}, results={results}"

    finally:
        # Cleanup
        try:
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
