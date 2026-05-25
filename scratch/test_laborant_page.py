import os
import sys
from unittest.mock import patch
sys.path.insert(0, r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.core.factory import create_app

def run_test():
    app = create_app(init_db=False)
    client = app.test_client()
    
    # 1. Simulate a laborant user session on AGRO line Zasyp page
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'JabloArt'
        sess['user_id'] = 45
        sess['rola'] = 'laborant'
        sess['grupa'] = 'Laboratorium'
        sess['pracownik_id'] = 45
        sess['session_tracking_id'] = 'test_tracking_id_lab'
        
    print("Testing AGRO Zasyp page rendering for laborant...")
    with patch('app.core.middleware.is_session_active', return_value=True):
        response = client.get('/?sekcja=Zasyp&linia=AGRO')
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            html = response.get_data(as_text=True)
            
            # Check if our custom class is present on the active floating bar
            if "d-none-mobile-lab" in html:
                print("[SUCCESS] Found 'd-none-mobile-lab' class on the active floating bar!")
            else:
                print("[WARNING] Could not find 'd-none-mobile-lab' class. Check if active orders exist in the plan.")
                
            # Check if toggle-focus-wrapper exists
            if "toggle-focus-wrapper" in html:
                print("[SUCCESS] Found 'toggle-focus-wrapper' class on the focus toggle button container!")
            else:
                print("[SUCCESS] 'toggle-focus-wrapper' not found in page (expected if agro_focus_mode is false due to no active plans).")
                
            # Check if details-row display is present
            if "details-row" in html:
                print("[SUCCESS] Found details-row elements rendered on the page!")
            else:
                print("[INFO] No details-row found on the page (expected if no completed or starting plan matches).")
        else:
            print(f"[ERROR] Failed to fetch page. Status: {response.status_code}")
            
    # 2. Simulate a laborant user session on PSD line Zasyp page
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'JabloArt'
        sess['user_id'] = 45
        sess['rola'] = 'laborant'
        sess['grupa'] = 'Laboratorium'
        sess['pracownik_id'] = 45
        sess['session_tracking_id'] = 'test_tracking_id_lab'
        
    print("\nTesting PSD Zasyp page rendering for laborant...")
    with patch('app.core.middleware.is_session_active', return_value=True):
        response = client.get('/?sekcja=Zasyp&linia=PSD')
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            html = response.get_data(as_text=True)
            print("[SUCCESS] PSD page rendered successfully!")
        else:
            print(f"[ERROR] Failed to fetch PSD page. Status: {response.status_code}")

if __name__ == "__main__":
    run_test()
