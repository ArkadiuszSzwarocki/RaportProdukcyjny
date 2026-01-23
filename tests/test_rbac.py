import requests

BASE = 'http://127.0.0.1:8082'

s = requests.Session()

# 1. Login as admin
r = s.post(BASE + '/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
print('LOGIN ADMIN ->', r.status_code)

# 2. Create test user
r = s.post(BASE + '/admin/konto/dodaj', data={'login':'rbac_tester','haslo':'secret','rola':'planista','grupa':'G1'})
print('/admin/konto/dodaj ->', r.status_code)

# 3. Verify user appears in settings
r = s.get(BASE + '/admin/ustawienia/uzytkownicy')
print('/admin/ustawienia/uzytkownicy ->', r.status_code)
print('contains rbac_tester?', 'rbac_tester' in r.text)

# 4. Try login as new user and access planista
s2 = requests.Session()
r = s2.post(BASE + '/login', data={'login':'rbac_tester','haslo':'secret'}, allow_redirects=False)
print('LOGIN RBAC ->', r.status_code)
if r.status_code in (302,200):
    r2 = s2.get(BASE + '/planista')
    print('/planista as rbac_tester ->', r2.status_code)
else:
    print('Login failed for rbac_tester')
