import requests

BASE = 'http://127.0.0.1:8082'

s = requests.Session()
print('POST /login...')
r = s.post(BASE + '/login', data={'login':'admin','haslo':'masterkey'}, allow_redirects=True)
print('POST status', r.status_code)
print('GET /?sekcja=Workowanie')
d = s.get(BASE + '/?sekcja=Workowanie')
print('GET status', d.status_code, 'len', len(d.text))
with open('tools/login_test_response.html', 'w', encoding='utf-8') as f:
    f.write(d.text)
print('Saved tools/login_test_response.html')
