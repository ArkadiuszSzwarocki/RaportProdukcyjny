import requests
import pytest

# Skip module if server not available
try:
    requests.get('http://127.0.0.1:8082', timeout=1)
except requests.RequestException:
    pytest.skip("Server not running on 127.0.0.1:8082 - skipping network script", allow_module_level=True)

s = requests.Session()
url = 'http://127.0.0.1:8082/login'
resp = s.post(url, data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
print('Status:', resp.status_code)
print('Headers:', resp.headers)
if 'Location' in resp.headers:
    print('Redirect to', resp.headers['Location'])
else:
    print('Response body snippet:', resp.text[:400])

# Try planista
s2 = requests.Session()
resp2 = s2.post(url, data={'login':'planista','haslo':'planista123'}, allow_redirects=False)
print('\nPlanista Status:', resp2.status_code)
print('Headers:', resp2.headers)
if 'Location' in resp2.headers:
    print('Redirect to', resp2.headers['Location'])
else:
    print('Response body snippet:', resp2.text[:400])
