import requests
import pytest

# Skip smoke tests if server not reachable
try:
    requests.get('http://127.0.0.1:8082', timeout=1)
except requests.RequestException:
    pytest.skip("Server not running on 127.0.0.1:8082 - skipping smoke tests", allow_module_level=True)

BASE = 'http://127.0.0.1:8082'
ADMIN_LOGIN = 'admin'
ADMIN_PASS = 'masterkey'

s = requests.Session()
print('Logging in...')
resp = s.post(BASE + '/login', data={'login': ADMIN_LOGIN, 'haslo': ADMIN_PASS}, allow_redirects=False, timeout=10)
print('Login status:', resp.status_code)
if resp.status_code not in (302, 200):
    print('Login may have failed; response:', resp.text[:200])

# Add employee
worker_name = 'Test Worker Smoke'
print('Adding worker:', worker_name)
resp = s.post(BASE + '/admin/pracownik/dodaj', data={'imie_nazwisko': worker_name}, allow_redirects=True, timeout=10)
print('Add worker status:', resp.status_code)

# Add user account
user_login = 'smoke_tester'
print('Adding user account:', user_login)
resp = s.post(BASE + '/admin/konto/dodaj', data={'login': user_login, 'haslo': 'Test1234', 'rola': 'produkcja'}, allow_redirects=True, timeout=10)
print('Add account status:', resp.status_code)

# Check admin users page
print('Fetching /admin/users')
resp = s.get(BASE + '/admin/users', timeout=10)
print('/admin/users status:', resp.status_code)
if user_login in resp.text:
    print('User found on /admin/users')
else:
    print('User NOT found on /admin/users')

# Check ustawienia page for worker
print('Fetching /admin/ustawienia')
resp = s.get(BASE + '/admin/ustawienia', timeout=10)
print('/admin/ustawienia status:', resp.status_code)
if worker_name in resp.text:
    print('Worker found on /admin/ustawienia')
else:
    print('Worker NOT found on /admin/ustawienia')

print('Smoke test finished.')
