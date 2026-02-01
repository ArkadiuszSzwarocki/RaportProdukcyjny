#!/usr/bin/env python3
import sys, os
from datetime import date
sys.path.insert(0, '.')
os.environ['PYTEST_CURRENT_TEST'] = 'test'
import app

with app.app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = 'admin'
        sess['rola'] = 'admin'
        sess['id'] = 1
        sess['pracownik_id'] = 1
    
    # Zapisz raport
    resp = client.post('/api/zapisz-raport-koncowy-global', data={'notatki': 'test uwagi'})
    print(f'Zapisz raport: {resp.status_code}')
    
    # Pobierz raport txt
    resp = client.post('/api/pobierz-raport', data={'format': 'email', 'data': str(date.today())})
    print(f'Pobierz TXT: {resp.status_code}')
    if resp.status_code == 200:
        txt = resp.get_data(as_text=True)
        print(f'Length: {len(txt)}, Has RAPORT: {"RAPORT" in txt}')
        if len(txt) < 500:
            print(f'Content:\n{txt}')
    else:
        print(f'Error: {resp.get_data(as_text=True)[:300]}')
