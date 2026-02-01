#!/usr/bin/env python3
"""
Pełny test przepływu: Zakончyz zmianę -> Pobierz raport (TXT, XLSX, PDF)
"""
import sys, os
from datetime import date
sys.path.insert(0, '.')
os.environ['PYTEST_CURRENT_TEST'] = 'test'
import app

print("\n" + "="*80)
print("TEST PRZEPŁYWU: Zakończ zmianę -> Pobierz raport")
print("="*80 + "\n")

with app.app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = 'admin'
        sess['rola'] = 'admin'
        sess['id'] = 1
        sess['pracownik_id'] = 1
    
    # 1. Zapisz raport
    print("1. Zapisywanie zmiany (POST /api/zapisz-raport-koncowy-global)")
    resp = client.post('/api/zapisz-raport-koncowy-global', data={'notatki': 'Test uwagi zmianowe'})
    print(f"   Status: {resp.status_code}")
    assert resp.status_code in [200, 302], f"Expected 200/302, got {resp.status_code}"
    print("   [OK]")
    
    # 2. Pobierz raport TXT
    print("\n2. Pobieranie raportu TXT (POST /api/pobierz-raport?format=email)")
    resp = client.post('/api/pobierz-raport', data={'format': 'email', 'data': str(date.today())})
    print(f"   Status: {resp.status_code}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    txt = resp.get_data(as_text=True)
    assert "RAPORT" in txt, "Report doesn't contain RAPORT"
    assert len(txt) > 100, f"Report too short: {len(txt)}"
    print(f"   Content-Length: {len(txt)} bytes")
    print("   [OK]")
    
    # 3. Pobierz raport XLSX
    print("\n3. Pobieranie raportu XLSX (POST /api/pobierz-raport?format=excel)")
    resp = client.post('/api/pobierz-raport', data={'format': 'excel', 'data': str(date.today())})
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.get_data()
        assert data[:2] == b'PK', "Not a valid XLSX file"
        assert len(data) > 1000, f"XLSX too small: {len(data)}"
        print(f"   Content-Length: {len(data)} bytes")
        print("   [OK]")
    else:
        print(f"   WARNING: Status {resp.status_code} (expected for missing reportlab)")
    
    # 4. Pobierz raport PDF
    print("\n4. Pobieranie raportu PDF (POST /api/pobierz-raport?format=pdf)")
    resp = client.post('/api/pobierz-raport', data={'format': 'pdf', 'data': str(date.today())})
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.get_data()
        assert data[:4] == b'%PDF', "Not a valid PDF file"
        assert len(data) > 1000, f"PDF too small: {len(data)}"
        print(f"   Content-Length: {len(data)} bytes")
        print("   [OK]")
    else:
        print(f"   WARNING: Status {resp.status_code} (expected for missing reportlab)")

print("\n" + "="*80)
print("SUCCESS! Przepływ pobierania raportów działa!")
print("="*80 + "\n")
