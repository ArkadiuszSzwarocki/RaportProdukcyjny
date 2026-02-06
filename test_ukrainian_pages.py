#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test skript sprawdzający tłumaczenia ukraińskie na każdej stronie
"""
import requests
import re
from urllib.parse import urljoin

BASE_URL = "http://localhost:5000"

# Polskie znaki których szukamy (łącząc hardcoded teksty)
POLISH_PATTERNS = [
    r'\bDodaj\b', r'\bEdytuj\b', r'\bUsuń\b', r'\bPlan\b',
    r'\bProdukt\b', r'\bStatus\b', r'\bAkcje\b', r'\bAnuluj\b',
    r'\bPotwierdź\b', r'\bZamknij\b', r'\bWysłij\b',
    r'\bGodzina\b', r'\bData\b', r'\bZapłanowane\b', r'\bZakończone\b',
    r'\bBlad\b', r'\bSukces\b', r'\bInformacje\b', r'\bUstawienia\b',
    r'\bPanelista\b', r'\bMagazyn\b', r'\bObsada\b', r'\bJakość\b',
    r'\bZarząd\b', r'\bMoje godziny\b', r'\bStrona główna\b'
]

# Ukraińskie znaki które powinny być
UKRAINIAN_PATTERNS = [
    r'\bУкраї', r'\bДобавити\b', r'\bОновити\b', r'\bВидалити\b',
    r'\bПлан\b', r'\bПродукт\b', r'\bСтатус\b', r'\bДія\b',
    r'\bСкасувати\b', r'\bЗакрити\b', r'\bВідправити\b',
]

def test_page(page_name, url, session_data=None):
    """Test jednej strony"""
    try:
        # Tworzenie sesji z ustawiono jezyka na ukrainski
        headers = {}
        cookies = {'app_language': 'uk'} if session_data is None else session_data
        
        response = requests.get(
            urljoin(BASE_URL, url),
            headers=headers,
            cookies=cookies,
            timeout=5
        )
        
        if response.status_code != 200:
            return {
                'page': page_name,
                'url': url,
                'status': f'ERROR {response.status_code}',
                'polish_texts': 0,
                'ukrainian_texts': 0
            }
        
        html = response.text.lower()
        
        # Szukamy polskich tekstów
        polish_found = []
        for pattern in POLISH_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                polish_found.extend(matches)
        
        # Szukamy ukraińskich
        ukrainian_found = []
        for pattern in UKRAINIAN_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                ukrainian_found.extend(matches)
        
        return {
            'page': page_name,
            'url': url,
            'status': 'OK',
            'polish_texts': len(set(polish_found)),
            'ukrainian_texts': len(set(ukrainian_found)),
            'likely_translated': len(set(ukrainian_found)) > 0
        }
    except Exception as e:
        return {
            'page': page_name,
            'url': url,
            'status': f'EXCEPTION: {str(e)[:50]}',
            'polish_texts': 0,
            'ukrainian_texts': 0
        }

# Strony do testowania
pages_to_test = [
    ('Login', '/login'),
    ('Dashboard', '/dashboard'),
    ('Planista', '/planista'),
    ('Magazyn', '/magazyn'),
    ('Obsada', '/obsada'),
    ('Jakość', '/jakosc'),
    ('Zarząd', '/zarzad'),
    ('Ustawienia', '/ustawienia'),
    ('Moje Godziny', '/moje_godziny'),
    ('Raporty', '/raporty_okresowe'),
    ('Bufor', '/bufor'),
]

print("=" * 80)
print("TESTOWANIE TŁUMACZEŃ UKRAIŃSKICH NA KAŻDEJ STRONIE")
print("=" * 80)
print()

results = []
for page_name, url in pages_to_test:
    result = test_page(page_name, url)
    results.append(result)
    
    status_icon = "✓" if result['status'] == 'OK' else "✗"
    print(f"{status_icon} {page_name:20} | URL: {url:25} | Status: {result['status']}")
    if result['status'] == 'OK':
        print(f"    Polskie: {result['polish_texts']}, Ukraińskie: {result['ukrainian_texts']}")
    print()

print("=" * 80)
print("PODSUMOWANIE")
print("=" * 80)
ok_count = sum(1 for r in results if r['status'] == 'OK')
translated_count = sum(1 for r in results if r.get('likely_translated', False))
print(f"Stron dostępnych: {ok_count}/{len(pages_to_test)}")
print(f"Stron z ukraińskim: {translated_count}/{ok_count}")
