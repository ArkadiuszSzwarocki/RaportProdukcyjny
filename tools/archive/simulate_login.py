import requests
import sys

BASE = 'http://localhost:8082'
LOGIN = 'Admin'
PASSWORD = 'Masterkey'

s = requests.Session()
try:
    print('POST /login')
    r = s.post(f'{BASE}/login', data={'login': LOGIN, 'haslo': PASSWORD}, allow_redirects=True, timeout=10)
    print('->', r.status_code, r.url)
    print('Cookies after login:', s.cookies.get_dict())

    r_root = s.get(f'{BASE}/', allow_redirects=True, timeout=10)
    print('GET / ->', r_root.status_code, r_root.url)

    r_section = s.get(f'{BASE}/?sekcja=Magazyn', timeout=10)
    print('GET /?sekcja=Magazyn ->', r_section.status_code)
    if 'Wylog' in r_section.text or 'Wyloguj' in r_section.text:
        print('Found logout link in page (likely logged in)')
    else:
        print('Logout link not found in page content')

    r_ping = s.post(f'{BASE}/api/session/ping', timeout=10)
    print('POST /api/session/ping ->', r_ping.status_code)

    print('Final cookies:', s.cookies.get_dict())
except Exception as e:
    print('Error during simulation:', e)
    sys.exit(2)

print('Simulation finished')
