import traceback
import sys, os

# Ensure repository root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app

app.testing = True

with app.test_client() as c:
    # Ustawiamy sesję jako zalogowany lider/admin
    with c.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['rola'] = 'admin'
    try:
        resp = c.post('/zamknij_zmiane', data={'uwagi_lidera': 'test z automatu'}, follow_redirects=True)
        print('STATUS', resp.status_code)
        print(resp.data.decode()[:2000])
    except Exception:
        traceback.print_exc()
