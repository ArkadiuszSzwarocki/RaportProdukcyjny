import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.factory import create_app
from app.db import get_db_connection

app = create_app()

def run_test():
    with app.test_client() as client:
        # Mock login as masteradmin
        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'testmaster'
            sess['rola'] = 'masteradmin'
            sess['grupa'] = 'ALL'
        
        # We need an active plan
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM plan_produkcji WHERE status='w toku' AND linia='AGRO' LIMIT 1")
        plan = cursor.fetchone()
        
        if not plan:
            print("No active AGRO plan to test.")
            return

        plan_id = plan['id']
        
        # Test start etap 1
        resp = client.post('/zasyp_etap_start', data={
            'plan_id': plan_id,
            'linia': 'AGRO',
            'etap': 1,
            'szarza_nr': 100,
            'auto_szarza_mode': 'auto',
            'wielkosc_szarzy_kg': 2000
        }, follow_redirects=True)
        
        print(f"Status Code: {resp.status_code}")
        text = resp.get_data(as_text=True)
        if 'zapisany' in text or 'Start etapu' in text or 'AUTO ZASYP' in text:
            print("Success string found in response!")
        else:
            print("Could not find success message.")
            
        cursor.execute("SELECT * FROM szarze WHERE plan_id=%s ORDER BY id DESC LIMIT 1", (plan_id,))
        sz = cursor.fetchone()
        print("Latest szarza:", sz)
        
        cursor.execute("SELECT * FROM zasyp_etapy WHERE plan_id=%s AND linia='AGRO' ORDER BY id DESC LIMIT 1", (plan_id,))
        ze = cursor.fetchone()
        print("Latest zasyp_etapy:", ze)
        
        conn.close()

if __name__ == '__main__':
    run_test()
    os._exit(0)
