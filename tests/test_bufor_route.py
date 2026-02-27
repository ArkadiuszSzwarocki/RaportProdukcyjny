import sys
from app import create_app
from app.db import get_db_connection
from unittest.mock import patch

# Simulate a logged-in user - mock the login_required decorator
def mock_login_required(f):
    return f

app = create_app()

# Test if route exists
with app.app_context():
    # Mock get_db_connection for testing
    mock_conn = type('obj', (object,), {
        'cursor': lambda: type('obj', (object,), {
            'execute': lambda *args, **kwargs: None,
            'fetchall': lambda: [
                (1, '2026-02-11', 'AGRO MILK TOP', 11680.0, 0, 0, 'zakonczone', 609)
            ],
            'close': lambda: None
        })(),
        'close': lambda: None,
        'is_connected': lambda: True
    })()
    
    # Test if the /bufor route is registered
    print("Registered routes:")
    for rule in app.url_map.iter_rules():
        if 'bufor' in str(rule):
            print(f"  {rule}")
    
    # Try to simulate a request
    with app.test_client() as client:
        resp = client.get('/bufor')
        print(f"\nStatus code: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        print(f"First 300 chars: {resp.data[:300]}")
