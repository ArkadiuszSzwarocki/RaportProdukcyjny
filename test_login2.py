import requests

session = requests.Session()

print("[*] Step 1: POST to /login with credentials")
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True,      
                  timeout=10)

print(f"Response status: {r.status_code}")
print(f"Final URL: {r.url}")
print(f"Session cookies: {session.cookies.get_dict()}")

# Check if login page is rendered
if 'form' in r.text and 'login' in r.text.lower():
    print("✗ Form found in response - still on login page")
else:
    print("✓ No login form - seems logged in!")
    
# Try to get dashboard directly
print("\n[*] Step 2: Try to access dashboard")
dash = session.get('http://localhost:8082/?sekcja=Zasyp', timeout=10)
print(f"Dashboard status: {dash.status_code}")
print(f"Dashboard URL: {dash.url}")

if 'plan_produkcji' in dash.text or 'STATUS' in dash.text or 'Zasyp' in dash.text:
    print("✓ Dashboard content found - logged in!")
elif 'login' in dash.url or 'form' in dash.text.lower():
    print("✗ Redirected to login - not logged in")
else:
    print("? Unknown state")
