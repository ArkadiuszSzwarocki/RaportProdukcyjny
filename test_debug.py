#!/usr/bin/env python
"""
Detailed test of synchronization with debug output.
"""

import requests
from datetime import date

session = requests.Session()
base_url = "http://localhost:8082"

# Login
login_data = {'login': 'admin', 'haslo': 'admin123'}
session.post(f"{base_url}/login", data=login_data, allow_redirects=True)

# Test: Try to start plan 467 (Workowanie) when 460 (Zasyp) is active
print("[TEST] Try to start Workowanie plan 467 while Zasyp plan 460 is active")
print("  Expected: BLOCK with warning")
print("  Actual:")

r = session.post(f"{base_url}/start_zlecenie/467", 
                   data={'sekcja': 'Workowanie'},
                   allow_redirects=True)

# Check for warning/success
if '⏸️' in r.text or 'Na Zasyp trwa' in r.text:
    print("  ✓ BLOCKED - synchronization working!")
elif '✅' in r.text or 'Uruchomiono' in r.text:
    print("  ✗ ALLOWED - synchronization NOT working!")
else:
    print(f"  ? Unknown response (status: {r.status_code})")
    # Look for flash messages
    import re
    flashes = re.findall(r'<div[^>]*class="[^"]*alert[^"]*"[^>]*>([^<]+)<', r.text)
    if flashes:
        print(f"  Flash messages: {flashes}")

# Check messages
if 'warning' in r.text:
    print("  - Found CSS class 'warning'")
if 'success' in r.text:
    print("  - Found CSS class 'success'")
