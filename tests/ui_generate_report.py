import requests
import os

BASE = 'http://127.0.0.1:8082'
LOGIN_URL = BASE + '/login'
ZAMKNIJ_URL = BASE + '/zamknij_zmiane'

s = requests.Session()
# Login jako admin (hasło z db.py: masterkey)
resp = s.post(LOGIN_URL, data={'login':'admin','haslo':'masterkey'}, allow_redirects=False)
print('Login status:', resp.status_code, 'Location:', resp.headers.get('Location'))

# Wyślij zamknięcie zmiany
resp2 = s.post(ZAMKNIJ_URL, data={'uwagi_lidera':'Test wygenerowania raportu przez UI'}, allow_redirects=False)
print('/zamknij_zmiane status:', resp2.status_code)

# Wypisz pliki w katalogu raporty
rap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'raporty'))
print('Raporty dir:', rap_dir)
print(os.listdir(rap_dir))
