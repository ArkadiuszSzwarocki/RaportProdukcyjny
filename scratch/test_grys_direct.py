import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.core.factory import create_app

app = create_app(init_db=False)
client = app.test_client()

# Let's mock the db or query helpers so we don't hit the DB if not needed, or just let it hit the test DB
# Let's run a request using the test client with GrysDawi's session
with client.session_transaction() as sess:
    sess['zalogowany'] = True
    sess['login'] = 'GrysDawi'
    sess['user_id'] = 40
    sess['rola'] = 'pracownik'
    sess['grupa'] = 'PSD'
    sess['pracownik_id'] = 40
    sess['session_tracking_id'] = 'test_tracking_id'

# Let's patch the middleware/is_session_active if it exists to return True
from unittest.mock import patch

with patch('app.core.middleware.is_session_active', return_value=True):
    response = client.get('/')
    print("STATUS CODE:", response.status_code)
    print("LOCATION:", response.headers.get('Location'))
