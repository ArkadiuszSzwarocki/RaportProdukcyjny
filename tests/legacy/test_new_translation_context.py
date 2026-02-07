#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test tłumaczeń z query parametrem i Accept-Language header
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app

def test_translation(test_name, url, accept_lang=None):
    """Testuj tłumaczenie"""
    client = app.test_client()
    headers = {}
    if accept_lang:
        headers['Accept-Language'] = accept_lang
    
    response = client.get(url, headers=headers)
    html = response.get_data(as_text=True).lower()
    
    print(f"\n{test_name}")
    print(f"  URL: {url}")
    if accept_lang:
        print(f"  Accept-Language: {accept_lang}")
    print(f"  Status: {response.status_code}")
    
    # Szukamy polskich tekstów (które NIE powinny być tam)
    polish = ['wejdź', 'hasło', 'login', 'zaloguj']
    polish_found = [p for p in polish if p in html]
    
    # Szukamy ukraińskich (które POWINNY być tam)
    ukrainian = ['увійти', 'пароль', 'логін']
    ukrainian_found = [u for u in ukrainian if u in html]
    
    print(f"  Polish texts found: {polish_found if polish_found else 'None (GOOD!)'}")
    print(f"  Ukrainian texts found: {ukrainian_found if ukrainian_found else 'None'}")
    
    return {
        'test': test_name,
        'polish_count': len(polish_found),
        'ukrainian_count': len(ukrainian_found),
        'expected_uk': len(ukrainian_found) > 0 if 'uk' in (accept_lang or 'pl') else False
    }

print("=" * 80)
print("TESTOWANIE TŁUMACZEŃ - NOWY CONTEXT PROCESSOR")
print("=" * 80)

results = []

# Test 1: Login bez parametrów - domyślnie polski
results.append(test_translation(
    "Test 1: Login domyślnie (PL)",
    "/login"
))

# Test 2: Login z query parametrem uk
results.append(test_translation(
    "Test 2: Login z ?lang=uk",
    "/login?lang=uk"
))

# Test 3: Login z Accept-Language: uk
results.append(test_translation(
    "Test 3: Login z Accept-Language: uk",
    "/login",
    accept_lang="uk,en;q=0.9,pl;q=0.8"
))

# Test 4: Login z Accept-Language: en
results.append(test_translation(
    "Test 4: Login z Accept-Language: en",
    "/login",
    accept_lang="en-US,en;q=0.9"
))

print("\n" + "=" * 80)
print("PODSUMOWANIE")
print("=" * 80)
for r in results:
    status = "✓" if r['polish_count'] == 0 else "⚠"
    print(f"{status} {r['test']}: PL={r['polish_count']}, UK={r['ukrainian_count']}")
