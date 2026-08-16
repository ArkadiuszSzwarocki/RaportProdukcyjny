import re
import requests
import sys

BASE = 'http://127.0.0.1:8082'

def main():
    s = requests.Session()
    print('Logging in...')
    r = s.post(BASE + '/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=True)
    print('Login status', r.status_code)
    if r.status_code != 200:
        print('Login failed, abort')
        sys.exit(1)

    print('Fetching Zasyp dashboard to locate szarza link...')
    d = s.get(BASE + '/?sekcja=Zasyp')
    if d.status_code != 200:
        print('Failed to fetch dashboard', d.status_code)
        sys.exit(2)
    m = re.search(r"/api/szarza_page/(\d+)", d.text)
    if not m:
        print('NO_SZARZA_LINK')
        sys.exit(3)
    plan_id = m.group(1)
    print('Found plan_id', plan_id)

    post_url = BASE + f'/api/dodaj_palete/{plan_id}'
    payload = {'waga_palety':'100', 'sekcja':'Zasyp'}
    headers = {'X-Requested-With':'XMLHttpRequest'}
    print('POST', post_url, 'payload', payload)
    resp = s.post(post_url, data=payload, headers=headers)
    print('POST status', resp.status_code)
    try:
        print('Response JSON:', resp.json())
    except Exception:
        print('Response text:', resp.text[:1000])

if __name__ == '__main__':
    main()
