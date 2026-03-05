#!/usr/bin/env python
"""Verify button is visible on page"""
import sys
sys.path.insert(0, '.')

from app.core.factory import create_app
app = create_app()

with app.test_client() as client:
    # Logowanie
    response = client.post('/login', data={
        'login': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    
    # Odczytaj planista page
    response = client.get('/planista')
    
    if response.status_code == 200:
        html = response.get_data(as_text=True)
        if 'Przenieś niezrealizowane' in html:
            print('✅ Przycisk "Przenieś niezrealizowane" JEST na stronie HTML')
        else:
            print('❌ Przycisk "Przenieś niezrealizowane" BRAK na stronie HTML')
        
        # Check if has_incomplete_plans logic
        if 'has_incomplete_plans' in html or 'Przenieś' in html:
            print('✅ JavaScript do przeniesienia jest na stronie')
        else:
            print('❌ JavaScript do przeniesienia BRAK')
    else:
        print(f'❌ Błąd: {response.status_code}')
