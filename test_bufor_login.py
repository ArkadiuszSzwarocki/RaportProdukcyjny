#!/usr/bin/env python3
"""Test bufor page with proper session login."""
import requests
from urllib.parse import urljoin

BASE_URL = "http://localhost:8082"
session = requests.Session()

# Step 1: Login
print("[*] Logging in...")
login_data = {'login': 'admin', 'haslo': 'admin123'}
login_resp = session.post(urljoin(BASE_URL, '/login'), data=login_data, allow_redirects=True)
print(f"    Login status: {login_resp.status_code}")
print(f"    Login headers: {dict(login_resp.headers)}")
print(f"    Set-Cookie header: {login_resp.headers.get('set-cookie', 'NOT FOUND')}")
print(f"    Session cookies after POST: {session.cookies.get_dict()}")
print(f"    Response text (first 300 chars): {login_resp.text[:300] if login_resp.text else 'EMPTY'}")

# Step 2: Check dashboard first to verify we're logged in
print("[*] Checking / (dashboard)...")
dashboard_resp = session.get(urljoin(BASE_URL, '/'), allow_redirects=False)
print(f"    Dashboard status: {dashboard_resp.status_code}")
print("[*] Accessing /bufor?data=2026-02-07...")
bufor_resp = session.get(urljoin(BASE_URL, '/bufor?data=2026-02-07'), allow_redirects=False)
print(f"    Bufor status: {bufor_resp.status_code}")

if bufor_resp.status_code == 200:
    # Check if we have data in the response
    if 'BUFOR' in bufor_resp.text or 'bufor' in bufor_resp.text.lower():
        print("    [OK] Got bufor page")
        if '<tbody>' in bufor_resp.text:
            rows = bufor_resp.text.count('<tr')
            print(f"         Found {rows} table rows")
        if 'Brak towaru' in bufor_resp.text or 'brak_towaru' in bufor_resp.text:
            print("         [!] Empty state message found - NO ORDERS SHOWING")
        else:
            print("         [OK] Orders appear to be present")
    else:
        print("    [!] Response doesn't look like bufor page")
        print(bufor_resp.text[:200])
else:
    print(f"    [!] Got status {bufor_resp.status_code} - expected 200")
    print(bufor_resp.text[:300])
