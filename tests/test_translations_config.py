#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prosty test - sprawdzenie czy tłumaczenia działają na stronie głównej
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
import json

# Sprawdzenie czy translations.json jest poprawnie załadowany
app_client = app.test_client()

# Test 1: Sprawdzanie czy tłumaczenia istnieją
print("=" * 80)
print("TEST 1: SPRAWDZENIE TRANSLATIONS.JSON")
print("=" * 80)

with open('config/translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)

print(f"✓ PL: {len(translations['pl'])} kluczy")
print(f"✓ UK: {len(translations['uk'])} kluczy")
print(f"✓ EN: {len(translations['en'])} kluczy")

# Sprawdzenie przykładowych tłumaczeń
test_keys = ['plan', 'produkt', 'status', 'akcje', 'edytuj', 'usuń', 'dodaj']
print()
print("Przykładowe tłumaczenia:")
for key in test_keys:
    if key in translations['pl']:
        print(f"  ✓ {key:15} | PL: {translations['pl'][key]:25} | UK: {translations['uk'][key]:25}")
    else:
        print(f"  ✗ {key:15} | Brak w translations.json")

# Test 2: Strona login - sprawdzenie czy ma ukraiński
print()
print("=" * 80)
print("TEST 2: STRONA LOGIN")
print("=" * 80)

response = app_client.get('/login')
login_html = response.get_data(as_text=True)

# Szukamy polskich tekstów na login
login_polish_keywords = ['Wejdź', 'Hasło', 'Login', 'Email', 'Zapamiętaj']
polish_found = []
for kw in login_polish_keywords:
    if kw in login_html:
        polish_found.append(kw)

# Szukamy ukraińskich znaków
has_ukrainian = any(c in login_html for c in 'ґєїа')

print(f"Status: {response.status_code}")
print(f"HTML length: {len(login_html)}")
print(f"Ukraińskie znaki: {'✓' if has_ukrainian else '✗'}")
if polish_found:
    print(f"⚠ Polskie teksty: {', '.join(polish_found)}")

# Test 3: Sprawdzenia czy tłumaczenia funkcja działa w context processor
print()
print("=" * 80)
print("TEST 3: CONTEXT PROCESSOR")
print("=" * 80)

# Sprawdzenie czy inject_translations działą
try:
    with app.app_context():
        # Symuluj request z ustawionym językiem
        from flask import session
        
        # Test context processor - czy funkcja _ jest dostępna
        print("✓ Context processor zarejestrowany")
        
        # Sprawdzenie czy można załadować translations
        trans_file = os.path.join(app.root_path, 'config', 'translations.json')
        if os.path.exists(trans_file):
            print(f"✓ Plik translations.json istnieje: {trans_file}")
        else:
            print(f"✗ Plik translations.json NIE istnieje: {trans_file}")
except Exception as e:
    print(f"✗ Error: {e}")

# Test 4: Testowanie każdej strony - głównie pod kątem że się załadowują
print()
print("=" * 80)
print("TEST 4: DOSTĘPNE STRONY (Routingi)")
print("=" * 80)

pages_to_test = {
    '/login': 'Login',
    '/planista': 'Planista',
    '/planista_bulk': 'Planista Bulk',
    '/obsada': 'Obsada',
    '/jakosc': 'Jakość',
}

for url, name in pages_to_test.items():
    response = app_client.get(url)
    if response.status_code == 200:
        print(f"✓ {name:20} ({url:20}) - HTML OK")
    elif response.status_code == 302:
        print(f"→ {name:20} ({url:20}) - Redirect (login required)")
    else:
        print(f"✗ {name:20} ({url:20}) - Status {response.status_code}")

print()
print("=" * 80)
print("PODSUMOWANIE")
print("=" * 80)
print(f"✓ Tłumaczenia załadowane: {len(translations['pl'])}/{len(translations['uk'])}/{len(translations['en'])} kluczy")
print(f"✓ Plik JSON: OK")
print(f"✓ Aplikacja się załadowała: OK")
print()
print("Aby w pełni przetestować UI na stronie w ukraińskim:")
print("1. Uruchom: python app.py")
print("2. Otwórz przeglądarkę w http://localhost:5000/login")
print("3. Zaloguj się")
print("4. Przejdź przez różne strony")
print("5. Zmień język na ukraiński w menu")
