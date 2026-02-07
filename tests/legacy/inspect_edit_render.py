from db import get_db_connection
import requests
import pytest

def first_wpis():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, problem, czas_start, czas_stop, kategoria FROM dziennik_zmiany ORDER BY id LIMIT 1")
    r = cursor.fetchone()
    conn.close()
    return r

if __name__ == '__main__':
    row = first_wpis()
    if not row:
        print('No wpis found')
        raise SystemExit(1)
    id, problem, czas_start, czas_stop, kategoria = row
    print('DB values:', problem, czas_start, czas_stop, kategoria)
    # Skip when server not running
    try:
        requests.get('http://127.0.0.1:8082', timeout=1)
    except requests.RequestException:
        pytest.skip("Server not running on 127.0.0.1:8082 - skipping network script", allow_module_level=True)

    s = requests.Session()
    s.post('http://127.0.0.1:8082/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
    r = s.get(f'http://127.0.0.1:8082/edytuj/{id}')
    html = r.text
    print('Fetched /edytuj HTML length', len(html))
    # print form HTML
    start = html.find('<form')
    end = html.find('</form>')
    print('FORM HTML:\n', html[start:end+7])
    print('Contains problem snippet?', ('%s' % problem)[:50] in html)
    print('Contains kategoria?', (kategoria or '') in html)
    # print input snippets
    import re
    m = re.search(r'name="czas_start"[^>]*value="([^"]*)"', html)
    print('czas_start value attribute:', m.group(1) if m else '<not found>')
    m2 = re.search(r'name="czas_stop"[^>]*value="([^"]*)"', html)
    print('czas_stop value attribute:', m2.group(1) if m2 else '<not found>')
