from db import get_db_connection
import requests, os

# find first wpis id
def first_wpis():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT id FROM dziennik_zmiany ORDER BY id LIMIT 1")
    r = cursor.fetchone()
    conn.close()
    return r[0] if r else None

if __name__ == '__main__':
    id = first_wpis()
    print('first id:', id)
    if not id:
        print('No wpisy found')
    else:
        s = requests.Session()
        login = s.post('http://127.0.0.1:8082/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
        print('login', login.status_code)
        r = s.get(f'http://127.0.0.1:8082/edytuj/{id}')
        print('/edytuj status', r.status_code)
        # print small part of content to confirm
        print(r.text[:400])
