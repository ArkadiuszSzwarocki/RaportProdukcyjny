import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'planista'
        sess['rola'] = 'planista'
        sess['pracownik_id'] = None
    r = client.get('/moje_godziny')
    print('Status:', r.status_code)
    print(r.get_data(as_text=True)[:800])
