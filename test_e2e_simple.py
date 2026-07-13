#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from app.db import get_db_connection
from app.core.factory import create_app
import json

app = create_app()

print("\n=== Test: Dispatch pallet to production tank ===\n")

with app.test_client() as client:
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find a fresh pallet
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
        
        # 1. Dispatch
        print("\n1. Dispatching to BB02...")
        response = client.post('/agro/scanner/dispatch', json={
            'surowiec_id': pallet_id,
            'zbiornik': 'BB02',
            'ilosc': 500,
            'type': 'Surowiec',
            'linia': 'Agro'
        })
        
        print(f"   Response status: {response.status_code}")
        result = response.get_json()
        print(f"   Response data: {result}")
        success = result.get('success')
        message = result.get('message')
        
        if success:
            print("   SUCCESS - Dispatch worked")
        else:
            print(f"   FAILED - {message}")
            conn.close()
            exit(1)
        
        # 2. Check database
        print("\n2. Checking database...")
        cursor.execute("SELECT lokalizacja, stan_magazynowy FROM magazyn_surowce WHERE id = %s", (pallet_id,))
        updated = cursor.fetchone()
        
        lokalizacja = updated['lokalizacja']
        new_stock = float(updated['stan_magazynowy'])
        
        print(f"   lokalizacja: {lokalizacja}")
        print(f"   stan_magazynowy: {new_stock}kg (was {initial_stock}kg)")
        
        if lokalizacja == 'BB02':
            print("   SUCCESS - lokalizacja is BB02")
        else:
            print(f"   FAILED - lokalizacja is {lokalizacja}, expected BB02")
        
        # 3. Check ruch record
        print("\n3. Checking ruch record...")
        cursor.execute('''
            SELECT id, zbiornik, typ_ruchu, status, ilosc
            FROM magazyn_ruch
            WHERE surowiec_id = %s AND typ_ruchu = 'PRODUKCJA'
            ORDER BY id DESC LIMIT 1
        ''', (pallet_id,))
        ruch = cursor.fetchone()
        
        if ruch:
            zbiornik = ruch['zbiornik']
            print(f"   ruch_id: {ruch['id']}")
            print(f"   zbiornik: {zbiornik}")
            print(f"   status: {ruch['status']}")
            if zbiornik:
                print("   SUCCESS - zbiornik is set")
            else:
                print("   FAILED - zbiornik is empty")
        else:
            print("   FAILED - No ruch record found")
        
        # 4. Check API
        print("\n4. Checking API /agro/api/production_inventory_snapshot...")
        response = client.get('/agro/api/production_inventory_snapshot?show_empty=1')
        data = response.get_json()
        
        count = data.get('count', 0)
        print(f"   Response items: {count}")
        
        found = None
        for item in data.get('items', []):
            if item.get('surowiec_id') == pallet_id:
                found = item
                break
        
        if found:
            print("   SUCCESS - Pallet FOUND in inventory")
            print(f"      zbiornik: {found.get('zbiornik')}")
            print(f"      lokalizacja: {found.get('lokalizacja')}")
            print(f"      stan_systemowy: {found.get('stan_systemowy')}")
        else:
            print("   FAILED - Pallet NOT FOUND in inventory")
            if data.get('items'):
                print(f"      First item in response: {data['items'][0].get('nr_palety', 'N/A')}")
        
        conn.close()
        print("\n=== Test Complete ===\n")
