import os
import sys
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from flask import session
from app.core.factory import create_app
from unittest.mock import patch

app = create_app(init_db=False)
client = app.test_client()

with patch('app.core.middleware.is_session_active', return_value=True):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'GrysDawi'
        sess['user_id'] = 40
        sess['rola'] = 'pracownik'
        sess['grupa'] = 'PSD'
        sess['pracownik_id'] = 40
        sess['session_tracking_id'] = 'test_grys_tracking'

    # Get the index page
    print("\n--- GET / ---")
    res1 = client.get('/', follow_redirects=False)
    print("STATUS:", res1.status_code)
    print("HEADERS:", dict(res1.headers))
    
    if res1.status_code == 302:
        loc = res1.headers['Location']
        print(f"Redirected to: {loc}")
        res2 = client.get(loc)
        print("REDIRECT STATUS:", res2.status_code)
        # Check what template is rendered or what the section is
        # Since we can inspect the response text
        if "Dashboard PSD" in res2.get_data(as_text=True):
            print("FOUND 'Dashboard PSD' in response text!")
        else:
            print("NO 'Dashboard PSD' in response text.")
            
        if "Zasyp PSD" in res2.get_data(as_text=True):
            print("FOUND 'Zasyp PSD' in response text!")
        else:
            print("NO 'Zasyp PSD' in response text.")
            
        if "Dashboard Agro" in res2.get_data(as_text=True):
            print("FOUND 'Dashboard Agro' in response text!")
        else:
            print("NO 'Dashboard Agro' in response text.")
            
    else:
        print("NO REDIRECT!")
