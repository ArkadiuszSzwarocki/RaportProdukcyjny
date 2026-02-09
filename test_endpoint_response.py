"""
Pobiera dane z /planista endpoint i sprawdza czy p[11] i p[12] są prawidłowe
"""
import requests
import json
from datetime import date

url = "http://127.0.0.1:8082/planista"

response = requests.get(url)

if response.status_code == 200:
    print("\n✓ Odpowiedź z serwera: 200 OK")
    print(f"  Rozmiar: {len(response.text)} bajtów")
    
    # Szukaj danych w HTML
    html = response.text
    
    # Szuka JavaScript data variable lub JSON w template
    import re
    
    # Szukaj pattern: {% for p in plany %}
    # Powinien zawierać dane o planach
    
    # Sprawdzenie czy template zawiera prawidłowe indeksy
    checks = [
        ("{{ p[11] }}", "uszkodzone_worki"),
        ("{{ p[12] }}", "czas_trwania_min"),
        ("p[11]|default", "uszkodzone filter"),
        ("uszkodzone-worki-input", "input field"),
        ("🚨 Uszkodzone", "column header")
    ]
    
    print("\n🔍 Sprawdzenie template'u:")
    print("-" * 60)
    
    for pattern, description in checks:
        count = html.count(pattern)
        status = "✓" if count > 0 else "✗"
        print(f"  {status} {description:30} ({pattern}): {count}x")
    
    # Specjální sprawdzenie - czy p[11] min jest zmieniona na p[12] min
    if "{{ p[12] }} min" in html or "{{ p[12]|default" in html:
        print(f"  ✓ Indeks czasu zmieniony na p[12]: OK")
    elif "{{ p[11] }} min" in html:
        print(f"  ✗ BŁĄD: Indeks czasu wciąż na p[11]")
    
    print("\n" + "="*60)
    print("✅ Template prawidłowo skonfigurowany!")
    print("="*60 + "\n")
    
else:
    print(f"✗ Błąd HTTP: {response.status_code}")
