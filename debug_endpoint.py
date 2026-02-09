"""
Debug: Co dokładnie zwraca /planista?
"""
import requests

url = "http://127.0.0.1:8082/planista"

try:
    response = requests.get(url, timeout=5)
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    print(f"\n--- Pirmych 2000 znaków HTML ---\n")
    print(response.text[:2000])
    
except Exception as e:
    print(f"❌ Błąd połączenia: {e}")
    print("\n➜ Serwer może nie być dostępny!")
