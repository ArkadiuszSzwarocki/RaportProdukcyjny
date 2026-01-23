from db import get_db_connection
import requests, os
from datetime import datetime

# get first wpis id

def first_wpis():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id FROM dziennik_zmiany ORDER BY id LIMIT 1")
    r = cursor.fetchone()
    conn.close()
    return r[0] if r else None


def fetch_wpis(id):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id, data_wpisu, sekcja, problem, czas_start, czas_stop, status, kategoria FROM dziennik_zmiany WHERE id=%s", (id,))
    r = cursor.fetchone()
    conn.close()
    return r


if __name__ == '__main__':
    id = first_wpis()
    if not id:
        print('No wpisy found')
        raise SystemExit(1)

    before = fetch_wpis(id)
    print('Before:', before)

    s = requests.Session()
    login = s.post('http://127.0.0.1:8082/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
    print('login status', login.status_code)

    # prepare new values
    new_problem = (before[3] or '') + ' [test-edit]'
    new_kategoria = before[7] or 'awaria'
    new_czas_start = before[4] or datetime.now().strftime('%H:%M')
    new_czas_stop = datetime.now().strftime('%H:%M')

    r = s.post(f'http://127.0.0.1:8082/edytuj/{id}', data={
        'problem': new_problem,
        'kategoria': new_kategoria,
        'czas_start': new_czas_start,
        'czas_stop': new_czas_stop,
        'widok_powrotu': 'dashboard'
    }, allow_redirects=False)

    print('POST status', r.status_code)

    after = fetch_wpis(id)
    print('After:', after)

    if after and new_problem in (after[3] or ''):
        print('Edit saved successfully')
    else:
        print('Edit did not persist')
