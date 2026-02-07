import requests
from datetime import date
import re

session = requests.Session()
session.post('http://localhost:8082/login', data={'login': 'admin', 'haslo': 'admin123'})

for section in ['Zasyp', 'Workowanie']:
    r = session.get(f'http://localhost:8082/?sekcja={section}')
    
    # Find status patterns
    zaplanowane_count = r.text.count('p[3] == \'zaplanowane\'')
    w_toku_count = r.text.count('p[3] == \'w toku\'')
    zakonczone_count = r.text.count('p[3] == \'zakonczone\'')
    
    # Find product names and statuses
    products = re.findall(r'<strong class="text-primary">([^<]+)</strong>', r.text)
    status_matches = re.findall(r'status["\']?\s*:\s*["\']?(\w+)["\']?', r.text)
    
    print(f"\n{section}:")
    print(f"  Products found: {len(products)} - {products[:3]}")
    print(f"  Contains 'zaplanowane': {zaplanowane_count}")
    print(f"  Contains 'w toku': {w_toku_count}") 
    print(f"  Contains 'zakonczone': {zakonczone_count}")
    
    # Look for START button
    if 'btn-start' in r.text:
        print("  ✓ START button exists")
    else:
        print("  ✗ No START button found")
    
    if 'btn-stop' in r.text:
        print("  ✓ STOP button exists (something is running)")
    else:
        print("  ✗ No STOP button found")
