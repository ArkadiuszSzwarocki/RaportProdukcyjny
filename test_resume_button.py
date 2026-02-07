import requests
import re
from datetime import datetime

session = requests.Session()
base_url = "http://localhost:8082"

# Login as admin
login_data = {
    'login': 'admin',
    'haslo': 'admin123'
}

resp = session.post(f"{base_url}/login", data=login_data, allow_redirects=True)
print(f"[*] Login: {resp.status_code}")

# Get today's date
today = datetime.now().strftime("%Y-%m-%d")
print(f"[*] Today's date: {today}")

# Get dashboard for Zasyp section
resp = session.get(f"{base_url}/?sekcja=Zasyp")
print(f"[*] Dashboard (Zasyp): {resp.status_code}")

# Save HTML for inspection
with open('dashboard_html.txt', 'w', encoding='utf-8') as f:
    f.write(resp.text)
print("[*] Dashboard HTML saved to dashboard_html.txt")

# Check for resume form
if 'przywroc_zlecenie' in resp.text:
    print("✓ Found 'przywroc_zlecenie' in HTML")
else:
    print("✗ 'przywroc_zlecenie' NOT found in HTML")

# Check for Wznów button
if 'Wznów' in resp.text:
    print("✓ Found 'Wznów' button")
else:
    print("✗ 'Wznów' button NOT found")

