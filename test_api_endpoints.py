#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location("app_module", "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app

with app.test_client() as client:
    # Set session
    with client.session_transaction() as sess:
        sess['login'] = 'test_user'
        sess['role'] = 'laborant'
    
    print("=== TESTING API ENDPOINTS ===\n")
    
    # Test API endpoint for production inventory
    print("1. GET /agro/api/production_inventory_snapshot?show_empty=1")
    response = client.get('/agro/api/production_inventory_snapshot?show_empty=1')
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.get_json()
        print(f"   Success: {data.get('success')}")
        if data.get('inventory'):
            print(f"   Items count: {len(data['inventory'])}")
            # Find BB03
            for item in data['inventory']:
                if item.get('zbiornik') == 'BB03':
                    print(f"   ✓ FOUND BB03: {item.get('nazwa')}, Stan: {item.get('stan_systemowy')} kg")
        else:
            print("   (inventory empty)")
    else:
        print(f"   Error: {response.data}")
    
    # Test historia endpoint
    print("\n2. GET /agro/api/magazyn/surowce-w-produkcji/historia/BB03")
    response = client.get('/agro/api/magazyn/surowce-w-produkcji/historia/BB03')
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.get_json()
        print(f"   Success: {data.get('success')}")
        if data.get('historia'):
            print(f"   Historia count: {len(data['historia'])}")
            for h in data['historia'][:3]:
                print(f"   - {h.get('surowiec_nazwa')}: {h.get('ilosc')} kg, zbiornik: {h.get('zbiornik')}")
    else:
        print(f"   Error: {response.data}")
