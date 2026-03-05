import requests
import json

# Sprawdzenie czy endpoint istnieje i jaką daje odpowiedź
url = "http://localhost:8082/api/check_niezrealizowane"
payload = {"data": "2026-03-04"}
headers = {"Content-Type": "application/json"}

try:
    r = requests.post(url, json=payload, headers=headers, timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
    
    if r.status_code == 200:
        j = r.json()
        print(f"\nJSON Response:")
        print(json.dumps(j, indent=2, ensure_ascii=False))
    elif r.status_code == 401 or r.status_code == 403:
        print("BŁĄD: Nie jesteś zalogowany lub brak uprawnień!")
    else:
        print(f"BŁĄD: Serwer zwrócił {r.status_code}")
        
except Exception as e:
    print(f"BŁĄD POŁĄCZENIA: {e}")
