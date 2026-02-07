#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test skrypt sprawdzający tłumaczenia ukraińskie - używa Flask test client
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
import re

def test_page_with_client(page_name, url, language='uk'):
    """Test jednej strony używając Flask test client"""
    try:
        client = app.test_client()
        
        # Ustawiamy język na ukraiński
        response = client.get(
            url,
            headers={'Accept-Language': 'uk'}
        )
        
        if response.status_code not in [200, 302]:
            # 302 to redirect (login), sprawdzamy też te)
            if response.status_code == 302:
                # Wejdź na stronę która przesyłana
                return {
                    'page': page_name,
                    'url': url,
                    'status': f'REDIRECT {response.status_code}',
                    'note': f'Redirect to {response.location}'
                }
            return {
                'page': page_name,
                'url': url,
                'status': f'ERROR {response.status_code}',
            }
        
        html = response.get_data(as_text=True)
        
        # Sprawdzamy czy mamy ukraiński tekst
        # Szukamy konkretnych ukraińskich znaków
        has_ukrainian = any(c in html for c in 'ґєїа')  # Ukraińskie znaki
        has_nav_translated = 'Панель управління' in html or 'Насипання' in html or 'Буфер' in html
        
        # Szukamy polskiego tekstu - rzeczy którzy nie powinny być tam
        polish_keywords = ['Plan produkcji', 'Moje godziny', 'Obsada', 'Magazyn', 'Jakość']
        has_polish = any(kw in html for kw in polish_keywords if 'Hala Produkcyjna' not in kw)  # Hala może być OK
        
        result = {
            'page': page_name,
            'url': url,
            'status': 'OK',
            'has_ukrainian': has_ukrainian,
            'has_nav_translated': has_nav_translated,
            'has_polish': has_polish,
            'html_length': len(html)
        }
        
        return result
    except Exception as e:
        return {
            'page': page_name,
            'url': url,
            'status': f'EXCEPTION: {str(e)[:60]}',
        }

# Strony do testowania
pages_to_test = [
    ('Login', '/login', 'login'),
    ('Dashboard', '/dashboard', 'sht. dashboard'),
    ('Planista', '/planista', 'planista'),
    ('Magazyn', '/magazyn', 'magazyn'),
    ('Obsada', '/obsada', 'obsada'),
    ('Jakosc', '/jakosc', 'quality'),
    ('Zarzad', '/zarzad', 'management'),
    ('Ustawienia', '/ustawienia', 'settings'),
    ('Moje Godziny', '/moje_godziny', 'my hours'),
    ('Raporty', '/raporty_okresowe', 'reports'),
]

print("=" * 90)
print("TESTOWANIE TŁUMACZEŃ UKRAIŃSKICH NA KAŻDEJ STRONIE")
print("=" * 90)
print()

results = []
for page_name, url, desc in pages_to_test:
    result = test_page_with_client(page_name, url)
    results.append(result)
    
    if result['status'] == 'OK':
        status_icon = "✓" if result.get('has_ukrainian', False) else "?"
        polish_warn = " ⚠ POLSKIE TEKSTY!" if result.get('has_polish', False) else ""
        print(f"{status_icon} {page_name:15} | {url:25} | UA:{result['has_ukrainian']} | NAV_OK:{result['has_nav_translated']}{polish_warn}")
    else:
        print(f"✗ {page_name:15} | {url:25} | {result['status']}")
    print()

print("=" * 90)
print("PODSUMOWANIE")
print("=" * 90)
ok_count = sum(1 for r in results if r['status'] == 'OK')
ua_count = sum(1 for r in results if r.get('has_ukrainian', False))
polish_found = sum(1 for r in results if r.get('has_polish', False))

print(f"✓ Stron dostępnych: {ok_count}/{len(pages_to_test)}")
print(f"✓ Stron z украї: {ua_count}/{ok_count}")
if polish_found > 0:
    print(f"⚠ Stron z polskim tekstem: {polish_found}")
else:
    print(f"✓ Brak polskich tekstów na stronach - świetnie!")
