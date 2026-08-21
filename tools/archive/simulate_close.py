import requests
import sys

BASE = 'http://localhost:8082'
LOGIN = 'Admin'
PASSWORD = 'Masterkey'

s = requests.Session()
try:
    r = s.post(f'{BASE}/login', data={'login': LOGIN, 'haslo': PASSWORD}, allow_redirects=True, timeout=10)
    print('Login ->', r.status_code, r.url)

    r_home = s.get(f'{BASE}/', timeout=10)
    print('Before close GET / ->', r_home.status_code, r_home.url)

    print('POST /api/session/close')
    r_close = s.post(f'{BASE}/api/session/close', timeout=10)
    print('->', r_close.status_code)

    r_after = s.get(f'{BASE}/', allow_redirects=True, timeout=10)
    print('After close GET / ->', r_after.status_code, r_after.url)
    text = r_after.text.lower()
    if '/login' in r_after.url or 'logowanie' in text or 'haslo' in text or 'zaloguj' in text:
        print('Session appears to be logged out (login page returned)')
    else:
        print('Session still appears active')

except Exception as e:
    print('Error', e)
    sys.exit(2)

print('Done')
