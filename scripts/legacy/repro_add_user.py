import sys
import os
import traceback

# Ensure repository root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app

app.testing = True

with app.test_client() as c:
    # Ustawiamy sesję jako admin
    with c.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'
    try:
        resp = c.post('/admin/konto/dodaj', data={'login': 'testrunner', 'haslo': 'Test1234', 'rola': 'admin'}, follow_redirects=True)
        print('STATUS', resp.status_code)
        print(resp.data.decode()[:2000])
    except Exception:
        traceback.print_exc()
