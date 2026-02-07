import requests
import re

session = requests.Session()
base_url = "http://localhost:8082"

login_data = {
    'login': 'admin',
    'haslo': 'admin123'
}

session.post(f"{base_url}/login", data=login_data, allow_redirects=True)

# Check Zasyp section for resume button location
resp = session.get(f"{base_url}/?sekcja=Zasyp")

# Find zakonczone rows
zakonczone_sections = re.findall(r"zakonczone.*?</tr>", resp.text, re.DOTALL)
print(f"[*] Found {len(zakonczone_sections)} 'zakonczone' sections")

if zakonczone_sections:
    section = zakonczone_sections[0]
    if 'przywroc_zlecenie' in section:
        print("✓ Resume button found in completed orders section")
        if 'replay' in section:
            print("✓ Resume button uses replay icon")
    else:
        print("✗ Resume button NOT found in completed orders")

# Check if resume button is in planned orders section
zaplanowane_sections = re.findall(r"zaplanowane.*?</tr>", resp.text, re.DOTALL)
print(f"\n[*] Found {len(zaplanowane_sections)} 'zaplanowane' sections")

if zaplanowane_sections:
    section = zaplanowane_sections[0]
    if 'przywroc_zlecenie' in section:
        print("✗ Resume button still in planned orders (should be removed)")
    else:
        print("✓ Resume button NOT in planned orders (correct)")
