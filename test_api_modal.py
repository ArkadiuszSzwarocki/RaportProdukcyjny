#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.db import get_db_connection
from app.core.factory import create_app

app = create_app()

print("\n=== Checking API: production_inventory_snapshot ===\n")

with app.test_client() as client:
    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find a pallet that was just dispatched to BB02
        cursor.execute("""
            SELECT s.id, s.nr_palety, s.lokalizacja, s.stan_magazynowy
            FROM magazyn_surowce s
            WHERE s.lokalizacja = 'BB02' AND s.stan_magazynowy > 0
            LIMIT 1
        """)
        pallet = cursor.fetchone()
        
        if pallet:
            pallet_id = pallet['id']
            print(f"Found pallet at BB02: {pallet['nr_palety']} (ID={pallet_id}, stock={pallet['stan_magazynowy']:.0f}kg)")
            
            # Call the API
            print("\nCalling /agro/api/production_inventory_snapshot?show_empty=1...")
            response = client.get('/agro/api/production_inventory_snapshot?show_empty=1')
            data = response.get_json()
            
            count = data.get('count', 0)
            print(f"API returned {count} items")
            
            # Look for this pallet
            found = None
            for item in data.get('items', []):
                if item.get('surowiec_id') == pallet_id:
                    found = item
                    print(f"\nPallet FOUND in API response:")
                    print(f"  - zbiornik: {found.get('zbiornik')}")
                    print(f"  - lokalizacja: {found.get('lokalizacja')}")
                    print(f"  - stan_systemowy: {found.get('stan_systemowy')}")
                    print(f"  - nazwa: {found.get('nazwa')}")
                    break
            
            if not found:
                print(f"\nPallet NOT FOUND in API response")
                print(f"First 3 items in response:")
                for i, item in enumerate(data.get('items', [])[:3]):
                    print(f"  {i+1}. {item.get('zbiornik')} - {item.get('nazwa', 'PUSTY')}")
        else:
            print("No pallet found at BB02 with stock > 0")
        
        conn.close()
        print("\n=== Complete ===\n")
