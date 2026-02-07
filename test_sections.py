import requests

session = requests.Session()
base_url = "http://localhost:8082"

login_data = {
    'login': 'admin',
    'haslo': 'admin123'
}

session.post(f"{base_url}/login", data=login_data, allow_redirects=True)

# Check both sections
for sekcja in ['Zasyp', 'Workowanie', 'Magazyn']:
    resp = session.get(f"{base_url}/?sekcja={sekcja}")
    if 'przywroc_zlecenie' in resp.text:
        print(f"✓ '{sekcja}' section has 'Wznów' button")
    else:
        print(f"✗ '{sekcja}' section does NOT have 'Wznów' button")
