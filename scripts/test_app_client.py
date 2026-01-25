import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app

def smoke_tests():
    with app.test_client() as client:
        r = client.get('/')
        print(f"GET / -> {r.status_code} (len={len(r.data)})")
        r2 = client.get('/moje_godziny')
        print(f"GET /moje_godziny -> {r2.status_code} (len={len(r2.data)})")

if __name__ == '__main__':
    smoke_tests()
