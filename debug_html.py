import requests
from datetime import date
import re

session = requests.Session()
session.post('http://localhost:8082/login', data={'login': 'admin', 'haslo': 'admin123'})

r = session.get(f'http://localhost:8082/?sekcja=Zasyp')

# Find start_zlecenie forms
start_forms = re.findall(r'production\.start_zlecenie.*?id=(\d+)', r.text)
print(f"Found start_zlecenie forms: {start_forms}")

# Also try to find in action attribute
action_forms = re.findall(r'action="([^"]*production\.start_zlecenie[^"]*)"', r.text)
print(f"Found in action: {action_forms[:2] if action_forms else 'none'}")

# Show a snippet of HTML
import_start = r.text.find('zaplanowane')
if import_start > -1:
    print("\nSnippet around 'zaplanowane':")
    print(r.text[import_start:import_start+500])
