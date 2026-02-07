import requests
from datetime import date

session = requests.Session()
session.post('http://localhost:8082/login', data={'login': 'admin', 'haslo': 'admin123'})

# Check both Zasyp and Workowanie
for section in ['Zasyp', 'Workowanie']:
    r = session.get(f'http://localhost:8082/?sekcja={section}')
    if r.status_code == 200:
        import re
        plans = re.findall(r'<strong class="text-primary">([^<]+)</strong>', r.text)
        print(f'✓ {section}: {len(plans)} plans')
        if plans:
            print(f'  Examples: {plans[:2]}')
