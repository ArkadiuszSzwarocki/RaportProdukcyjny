from app import app
from flask import session
import logging

with app.test_request_context('/start_zlecenie/104', method='POST', data={
    'linia': 'AGRO',
    'sekcja': 'Workowanie',
    'typ_pakowania': 'Worki',
    'opakowanie_id': '43',  # Some folia ID
    'data_produkcji': '2026-06-20'
}):
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['login'] = 'test_operator'
            sess['rola'] = 'operator'
            sess['selected_hall_view'] = 'AGRO'
        
        response = client.post('/start_zlecenie/104', data={
            'linia': 'AGRO',
            'sekcja': 'Workowanie',
            'typ_pakowania': 'Worki',
            'opakowanie_id': '43',
            'data_produkcji': '2026-06-20'
        })
        
        print("Status code:", response.status_code)
        print("Headers:", response.headers)
        
        with client.session_transaction() as sess:
            print("Flashes:", dict(sess.get('_flashes', [])))
