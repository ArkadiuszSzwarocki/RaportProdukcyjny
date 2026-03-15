import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.factory import create_app

app = create_app()

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['login'] = 'test'
        sess['rola'] = 'planista'
        sess['pracownik_id'] = 1
        sess['zalogowany'] = True

    # simulate user submitting date in Polish format
    resp = c.get('/podsumowanie_szarz?period=day&date=12.03.2026')
    print('STATUS', resp.status_code)
    print(resp.data.decode('utf-8')[:4000])
