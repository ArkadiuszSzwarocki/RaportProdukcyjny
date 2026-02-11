import requests
from datetime import date

today = str(date.today())
url = f"http://localhost:8082/api/bufor?data_wybrana={today}"

try:
    resp = requests.get(url, cookies={"session": "dummy"})  # Without proper session this will redirect
    print(f"Status: {resp.status_code}")
    print(f"Content type: {resp.headers.get('content-type')}")
    
    # Try HTML endpoint instead
    resp2 = requests.get(f"http://localhost:8082/bufor", cookies={})
    print(f"\nHTML /bufor:")
    print(f"Status: {resp2.status_code}")
    print(f"Content-Type: {resp2.headers.get('content-type')}")
    
    if "zakonczone" in resp2.text:
        print("✓ Template zawiera status 'zakonczone'")
    if 'data-status="zakonczone"' in resp2.text:
        print("✓ Przycisk ma data-status='zakonczone'")
    if "AGRO MILK TOP" in resp2.text:
        print("✓ Są dane dla AGRO MILK TOP")
        
except Exception as e:
    print(f"Error: {e}")
