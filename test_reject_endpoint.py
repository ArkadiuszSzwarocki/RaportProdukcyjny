#!/usr/bin/env python
"""Test the reject endpoint using Flask test client."""
import sys
from app.core.factory import create_app

app = create_app()

# Create test client
with app.test_client() as client:
    # First, login to get a session
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['pracownik_id'] = 1  # Set a lider ID
        sess['rola'] = 'lider'    # Set lider role
    
    # Now try to reject request ID 6
    print("Testing POST /wnioski/6/reject...")
    response = client.post('/wnioski/6/reject', headers={
        'X-Requested-With': 'XMLHttpRequest'
    })
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.get_json() if response.is_json else response.get_data(as_text=True)}")
