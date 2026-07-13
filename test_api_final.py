#!/usr/bin/env python3
"""Test API endpoint with fixed @staticmethod."""

import sys
sys.path.insert(0, '.')

from app.core.factory import create_app

app = create_app()

with app.test_client() as client:
    # Login first
    client.post('/login', data={
        'login': 'admin',
        'haslo': 'admin',
    }, follow_redirects=True)
    
    print("=== Testing API /agro/api/production_inventory_snapshot ===\n")
    
    # Test endpoint
    response = client.get('/agro/api/production_inventory_snapshot?show_empty=1')
    print(f"Status: {response.status_code}")
    print(f"Response:\n{response.get_json()}")
    
    # Search for BB03 items
    data = response.get_json()
    if data.get('success') and data.get('items'):
        bb03_items = [item for item in data['items'] if item.get('zbiornik') == 'BB03']
        print(f"\n=== Items in BB03 ({len(bb03_items)}) ===")
        for item in bb03_items:
            print(f"  - {item.get('nazwa')} (ID: {item.get('surowiec_id')}, Stan: {item.get('stan_systemowy')} kg)")
