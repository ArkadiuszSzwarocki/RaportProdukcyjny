import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from app import create_app

def main():
    app = create_app()
    with app.test_client() as client:
        # We need to simulate a request to /warehouse/drukuj_etykiete/410
        # Since it's @login_required, we might get 302. Let's bypass login or just trigger the route function directly.
        
        with app.app_context():
            from app.blueprints.routes_warehouse import drukuj_etykiete
            from flask import g, session
            # Mock login session
            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['rola'] = 'admin'
                sess['user_id'] = 1
            
            try:
                # The route function takes paleta_id
                response = client.get('/warehouse/drukuj_etykiete/410')
                print(f"Status code: {response.status_code}")
                # If 500, the logger already logged it to console
            except Exception as e:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    main()
