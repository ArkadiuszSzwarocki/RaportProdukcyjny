import requests
from datetime import datetime
import re

session = requests.Session()
base_url = "http://localhost:8082"

# Login as admin
login_data = {
    'login': 'admin',
    'haslo': 'admin123'
}

print("[*] Logging in as admin...")
resp = session.post(f"{base_url}/login", data=login_data, allow_redirects=True)
print(f"    Status: {resp.status_code}")

# Get dashboard for Zasyp section with one planned order
resp = session.get(f"{base_url}/?sekcja=Zasyp")
print(f"\n[*] Loaded Zasyp dashboard: {resp.status_code}")

# Extract order ID from HTML for first zaplanowane order
matches = re.findall(r'/przywroc_zlecenie/(\d+)"', resp.text)
print(f"[*] Found {len(matches)} resume forms in HTML")

if matches:
    order_id = matches[0]
    print(f"[*] First order ID to resume: {order_id}")
    
    # Click resume button (simulate form submission)
    resume_resp = session.post(f"{base_url}/przywroc_zlecenie/{order_id}", allow_redirects=True)
    print(f"[*] Resume request status: {resume_resp.status_code}")
    
    if resume_resp.status_code == 200:
        print("✓ Resume endpoint returned 200 OK")
        # Check if order moved to w toku
        dashboard_resp = session.get(f"{base_url}/?sekcja=Zasyp")
        if 'w toku' in dashboard_resp.text.lower():
            print("✓ Order status likely changed to 'w toku'")
        else:
            print("? Unable to verify status change from HTML")
    else:
        print(f"✗ Resume request failed with status {resume_resp.status_code}")
else:
    print("✗ No resume forms found in HTML")

