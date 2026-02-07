import requests

session = requests.Session()

# Login first
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)
print("[✓] Logged in")

# Test AJAX endpoints
tests = [
    ('DELETE plan', 'POST', '/api/usun_plan_ajax/461'),
    ('START Workowanie', 'POST', '/start_zlecenie/460?sekcja=Workowanie'),
    ('Recover order', 'POST', '/api/przywroc_usunietego_zlecenia/461'),
    ('Edit plan AJAX', 'POST', '/api/edytuj_plan_ajax'),
]

for name, method, url in tests:
    try:
        full_url = f'http://localhost:8082{url}'
        if method == 'GET':
            r = session.get(full_url, timeout=5)
        else:
            r = session.post(full_url, timeout=5, 
                           data={'id': 461} if 'ajax' in url else {},
                           headers={'Content-Type': 'application/x-www-form-urlencoded'})
        
        status_symbol = '✓' if r.status_code < 400 else '✗'
        print(f"{status_symbol} {name:20s} {method:6s} {url:40s} => {r.status_code}")
    except Exception as e:
        print(f"✗ {name:20s} {method:6s} {url:40s} => ERROR: {e}")
