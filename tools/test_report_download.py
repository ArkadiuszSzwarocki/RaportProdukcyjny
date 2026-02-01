#!/usr/bin/env python3
"""
Test pobierania raportów endpoint /api/zamknij-zmiane-global

Użycie:
  python tools/test_report_download.py
"""
import sys
import os
from datetime import date

# Dodaj ścieżkę do głównego pakietu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ustaw zmienną środowiskową aby app.py nie uruchamiał db.setup_database() w testach
os.environ['PYTEST_CURRENT_TEST'] = 'test_report_download'

import app
import json

def test_report_download():
    """Test endpoint /api/zamknij-zmiane-global"""
    
    from flask import session
    
    with app.app.test_client() as client:
        # Login
        print("\n1. Logging in...")
        login_data = {
            'username': 'admin',
            'password': os.getenv('INITIAL_ADMIN_PASSWORD', 'admin123'),
        }
        response = client.post('/login', data=login_data, follow_redirects=True)
        print(f"   Status: {response.status_code}")
        
        # Teraz w kontekście testu Flask, użyj session
        with client.session_transaction() as sess:
            print(f"   Session keys: {list(sess.keys())}")
            if 'zalogowany' in sess:
                print(f"   Session 'zalogowany': {sess['zalogowany']}")
                print(f"   Session 'rola': {sess.get('rola', 'N/A')}")
            else:
                # Ustaw sesję ręcznie jeśli login nie zadziałał
                print(f"   WARNING: 'zalogowany' not in session, setting manually...")
                sess['zalogowany'] = 'admin'
                sess['rola'] = 'admin'
                sess['id'] = 1
        
        # Test endpoint zamknij-zmiane-global
        print("\n2. POSTing to /api/zamknij-zmiane-global...")
        date_str = str(date.today())
        response = client.post(f'/api/zamknij-zmiane-global', data={
            'date': date_str,
            'uwagi': 'Test uwagi zmianowe',
            'lider_name': 'Test Leader'
        }, follow_redirects=False)
        print(f"   Date: {date_str}")
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.content_type}")
        print(f"   Content-Disposition: {response.headers.get('Content-Disposition', 'N/A')}")
        print(f"   Content-Length: {len(response.get_data())}")
        
        # Sprawdź, czy jest ZIP
        if response.status_code == 200:
            data = response.get_data()
            # ZIP ma magiczne słowa: PK (0x504b)
            if data[:2] == b'PK':
                print("   OK ZIP file detected!")
                # Zapisz do pliku tymczasowego
                import zipfile
                from io import BytesIO
                try:
                    zip_obj = zipfile.ZipFile(BytesIO(data))
                    files_in_zip = zip_obj.namelist()
                    print(f"   Files in ZIP: {files_in_zip}")
                    print(f"   OK Report download successful!")
                    return True
                except Exception as e:
                    print(f"   ERROR Could not read ZIP: {e}")
                    return False
            else:
                print(f"   ERROR Response is not ZIP!")
                print(f"   First 200 bytes: {data[:200]}")
                return False
        else:
            print(f"   ERROR Expected 200, got {response.status_code}")
            print(f"   Response: {response.get_data(as_text=True)[:500]}")
            return False

if __name__ == '__main__':
    success = test_report_download()
    sys.exit(0 if success else 1)
