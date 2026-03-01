#!/usr/bin/env python
import requests

# Send POST request with login cookie (assuming session is not required for direct curl)
# But we need to get a session with proper authentication
# Let's use Flask test client instead but in a simpler way

from app.core.factory import create_app
from flask import Flask

app = create_app()

with app.test_client() as client:
    # Login and set session
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['pracownik_id'] = 1
        sess['rola'] = 'lider'
    
    # Make the request
    resp = client.post('/wnioski/6/reject', headers={
        'X-Requested-With': 'XMLHttpRequest'
    })
    
    print(f"Status: {resp.status_code}")
    print(f"Content-Type: {resp.content_type}")
    if resp.is_json:
        print(f"JSON Response: {resp.get_json()}")
    else:
        print(f"Text Response: {resp.get_data(as_text=True)[:500]}")
