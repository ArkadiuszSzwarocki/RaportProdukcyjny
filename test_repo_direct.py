#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.core.factory import create_app
from app.repositories.agro_tanks_repository import AgroTanksRepository

app = create_app()

print("\n=== Direct test: get_production_inventory() ===\n")

with app.app_context():
    # Call the repository function directly
    items = AgroTanksRepository.get_production_inventory(limit=500, linia='Agro')
    
    print(f"Total items returned: {len(items)}")
    
    if items:
        print(f"\nFirst 3 items:")
        for i, item in enumerate(items[:3]):
            print(f"  {i+1}. {item.get('zbiornik')} - {item.get('nr_palety')} ({item.get('stan_systemowy'):.0f}kg)")
    
    # Look for our test pallet
    print(f"\nSearching for pallet ID 533 (SUR000001779191722392)...")
    found = None
    for item in items:
        if item.get('surowiec_id') == 533:
            found = item
            break
    
    if found:
        print(f"FOUND in inventory:")
        print(f"  - zbiornik: {found.get('zbiornik')}")
        print(f"  - lokalizacja: {found.get('lokalizacja')}")
        print(f"  - nr_palety: {found.get('nr_palety')}")
        print(f"  - stan_systemowy: {found.get('stan_systemowy')}")
        print(f"  - rodzaj: {found.get('rodzaj')}")
    else:
        print(f"NOT FOUND in production inventory")
    
    print(f"\n=== Test Complete ===\n")
