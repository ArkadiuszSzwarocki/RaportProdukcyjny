import os
import sys
import time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from db import get_db_connection
from app import app
from datetime import date

def insert_test_plan():
    conn = get_db_connection(); cursor = conn.cursor()
    today = date.today()
    cursor.execute("INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status) VALUES (%s, %s, %s, %s, %s)", (today, 'Zasyp', 'TEST_PRODUKT', 100.0, 'w toku'))
    conn.commit()
    conn.close()

def check_and_run():
    # ensure no leftover files
    folder = 'raporty_temp'
    if os.path.exists(folder):
        for f in os.listdir(folder):
            os.remove(os.path.join(folder, f))

    insert_test_plan()

    app.testing = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'

    resp = client.post('/zamknij_zmiane', data={'uwagi_lidera': 'Automatyczny test'}, follow_redirects=True)
    print('POST status:', resp.status_code)

    # wait a bit for file IO
    time.sleep(1)
    files = []
    if os.path.exists(folder):
        files = os.listdir(folder)
    print('Files in raporty_temp:', files)

    # Check DB: last raporty_koncowe
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, data_raportu, lider_uwagi FROM raporty_koncowe ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    print('Last raporty_koncowe row:', row)
    cursor.execute("SELECT id, status FROM plan_produkcji WHERE produkt=%s ORDER BY id DESC LIMIT 1", ('TEST_PRODUKT',))
    p = cursor.fetchone(); print('Test plan row:', p)
    conn.close()


def cleanup_test_artifacts(test_product='TEST_PRODUKT', raport_uwagi='Automatyczny test'):
    """Usuń testowe rekordy i pliki wygenerowane przez test.

    - usuwa pliki z `raporty_temp`
    - usuwa wiersze z `plan_produkcji` gdzie `produkt`=test_product
    - usuwa wiersze z `raporty_koncowe` gdzie `lider_uwagi`=raport_uwagi i data_raportu=dzisiaj
    """
    folder = 'raporty_temp'
    if os.path.exists(folder):
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            try:
                os.remove(p)
                print('Usunięto plik:', p)
            except Exception as e:
                print('Nie udało się usunąć pliku', p, e)

    # Cleanup DB
    conn = get_db_connection(); cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM plan_produkcji WHERE produkt=%s", (test_product,))
        cursor.execute("DELETE FROM raporty_koncowe WHERE lider_uwagi=%s AND data_raportu=%s", (raport_uwagi, date.today()))
        conn.commit()
        print('Usunięto testowe rekordy z bazy danych.')
    except Exception as e:
        print('Błąd podczas cleanup DB:', e)
    finally:
        conn.close()


if __name__ == '__main__':
    check_and_run()
    cleanup_test_artifacts()


if __name__ == '__main__':
    check_and_run()
