import requests
import datetime

session = requests.Session()

# Login
r = session.post('http://localhost:8082/login',
                  data={'login': 'admin', 'haslo': 'admin123'},
                  allow_redirects=True)

# Try explicit date parameter
today = datetime.date.today().isoformat()
r = session.get(f'http://localhost:8082/?sekcja=Zasyp&data={today}')

import re
plan_ids = re.findall(r'data-id="(\d+)"', r.text)
print(f"[*] Dashboard for {today}")
print(f"[*] Plans found: {plan_ids}")

# Check if 472 is there
if '472' in plan_ids or 472 in [int(x) for x in plan_ids]:
    print("[OK] Test plan 472 is visible!")
else:
    # Check HTML
    if '472' in r.text:
        print("[!] Plan 472 found in HTML but not in data-id")
        # Print around 472
        idx = r.text.find('472')
        print(r.text[max(0, idx-200):idx+200])
    else:
        print("[!] Plan 472 not found anywhere")

# Print first 1000 chars of body
print("\n[HTML Content (first 2000 chars)]:")
print(r.text[:2000])
