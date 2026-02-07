import requests

session = requests.Session()

print("[*] Logging in as admin with password 'admin123'...")
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)

print(f"Status: {r.status_code}")

if r.status_code == 200:
    # Check if still on login page or redirected
    if 'login' in r.url or 'logowanie' in r.text.lower():
        print("✗ Still on login page - login FAILED")
        # Look for error message
        if 'błędne dane' in r.text or 'nieprawidłowe' in r.text:
            print("  Error: Invalid credentials message shown")
    else:
        print("✓ Redirected from login page - login SUCCESS")
        print(f"  Current URL: {r.url}")
        # Try to access dashboard
        dashboard = session.get('http://localhost:8082/?sekcja=Zasyp')
        if dashboard.status_code == 200:
            print("✓ Can access dashboard")
        else:
            print(f"✗ Cannot access dashboard (status {dashboard.status_code})")
