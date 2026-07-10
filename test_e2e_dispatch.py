#!/usr/bin/env python3
"""
End-to-end test: Scan pallet to BB02 -> verify it appears in production inventory modal
"""
import requests
import json
from app.db import get_db_connection
from app.core.factory import create_app

app = create_app()

# Fake scanner dispatch
print("\n=== Test: Dispatch pallet to production tank ===\n")

# Get app context
with app.test_client() as client:
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find a fresh pallet to test with
        cursor.execute("SELECT id, nr_palety, stan_magazynowy FROM magazyn_surowce WHERE stan_magazynowy > 0 LIMIT 1")
        pallet = cursor.fetchone()
        
        if not pallet:
            print("ERROR: No pallet with stock found!")
            conn.close()
            exit(1)
        
        pallet_id = pallet['id']
        pallet_nr = pallet['nr_palety']
        initial_stock = float(pallet['stan_magazynowy'])
        
        print(f"Test pallet: {pallet_nr} (ID={pallet_id}, stock={initial_stock}kg)")
        
        # 1. Call /dispatch endpoint with zbiornik='BB02'
        print("\n1. Dispatching to BB02...")
        response = client.post('/agro/scanner/dispatch', json={
            'barcode': str(pallet_nr),
            'zbiornik': 'BB02',
            'ilosc': 500
        })
        
        result = response.get_json()
        print(f"   Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if result.get('success'):
            print("   ✓ Dispatch successful")
        else:
            print(f"   ✗ Dispatch failed: {result.get('message')}")
            exit(1)
        
        # 2. Check database: lokalizacja should be 'BB02'
        print("\n2. Checking database lokalizacja...")
        cursor.execute("SELECT lokalizacja, stan_magazynowy FROM magazyn_surowce WHERE id = %s", (pallet_id,))
        updated = cursor.fetchone()
        
        print(f"   lokalizacja: '{updated['lokalizacja']}'")
        print(f"   stan_magazynowy: {updated['stan_magazynowy']}kg")
        
        if updated['lokalizacja'] == 'BB02':
            print("   ✓ lokalizacja updated correctly")
        else:
            print(f"   ✗ lokalizacja NOT updated (expected 'BB02', got '{updated['lokalizacja']}')")
        
        # 3. Check ruch record has zbiornik
        print("\n3. Checking ruch record...")
        cursor.execute('''
            SELECT id, zbiornik, typ_ruchu, status, ilosc
            FROM magazyn_ruch
            WHERE surowiec_id = %s AND typ_ruchu = 'PRODUKCJA'
            ORDER BY id DESC LIMIT 1
        ''', (pallet_id,))
        ruch = cursor.fetchone()
        
        if ruch:
            print(f"   ruch_id: {ruch['id']}")
            print(f"   zbiornik: '{ruch['zbiornik']}'")
            print(f"   typ_ruchu: {ruch['typ_ruchu']}")
            print(f"   status: {ruch['status']}")
            if ruch['zbiornik']:
                print("   ✓ zbiornik is set")
            else:
                print("   ✗ zbiornik is EMPTY")
        else:
            print("   ✗ No ruch record found!")
        
        # 4. Check if appears in production inventory
        print("\n4. Calling API /agro/api/production_inventory_snapshot...")
        with client:
            response = client.get('/agro/api/production_inventory_snapshot?show_empty=1')
            data = response.get_json()
            
            print(f"   Response items: {data.get('count', 0)}")
            
            found = None
            for item in data.get('items', []):
                if item.get('surowiec_id') == pallet_id:
                    found = item
                    break
            
            if found:
                print(f"   ✓ Pallet FOUND in inventory!")
                print(f"      zbiornik: {found.get('zbiornik')}")
                print(f"      lokalizacja: {found.get('lokalizacja')}")
                print(f"      stan_systemowy: {found.get('stan_systemowy')}")
            else:
                print(f"   ✗ Pallet NOT FOUND in inventory")
                print(f"      Available tanks: {[item.get('zbiornik') for item in data.get('items', []) if item.get('surowiec_id')]}")
        
        conn.close()
        print("\n=== Test Complete ===\n")
