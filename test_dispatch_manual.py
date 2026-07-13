#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Flask app from top-level module
import importlib.util
spec = importlib.util.spec_from_file_location("app_module", "app.py")
app_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_module)
app = app_module.app

from app.services.scanner_service import ScannerService

with app.app_context():
    # Test dispatch for ID 312 (nr_palety: SUR080520268225338153)
    surowiec_id = 312
    ilosc = 1000.0
    zbiornik = 'BB03'
    
    print(f"=== TESTUJĘ DISPATCH ===")
    print(f"Surowiec ID: {surowiec_id}")
    print(f"Ilość: {ilosc}")
    print(f"Zbiornik: {zbiornik}\n")
    
    try:
        ok, msg = ScannerService.dispatch_to_production(
            surowiec_id=surowiec_id,
            ilosc=ilosc,
            worker_login='test_user',
            linia='AGRO',
            plan_id=None,
            zbiornik=zbiornik,
            komentarz='Test dispatch',
            pallet_type='Surowiec'
        )
        
        print(f"Result: {ok}")
        print(f"Message: {msg}")
        
        if ok:
            print("\n✅ Dispatch successful!")
            
            # Verify in database
            from app.db import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            
            # Check magazyn_surowce
            cur.execute("""
                SELECT id, nazwa, stan_magazynowy, lokalizacja 
                FROM magazyn_surowce WHERE id = %s
            """, (surowiec_id,))
            row = cur.fetchone()
            if row:
                print(f"\nmagazyn_surowce updated:")
                print(f"  Stan: {row['stan_magazynowy']} kg")
                print(f"  Lokalizacja: {row['lokalizacja']}")
            
            # Check last move in magazyn_ruch
            cur.execute("""
                SELECT typ_ruchu, ilosc, zbiornik, status, autor_data
                FROM magazyn_ruch 
                WHERE surowiec_id = %s 
                ORDER BY id DESC LIMIT 1
            """, (surowiec_id,))
            ruch = cur.fetchone()
            if ruch:
                print(f"\nmagazyn_ruch last entry:")
                print(f"  Typ: {ruch['typ_ruchu']}")
                print(f"  Ilość: {ruch['ilosc']}")
                print(f"  Zbiornik: {ruch['zbiornik']}")
                print(f"  Status: {ruch['status']}")
            
            cur.close()
            conn.close()
        else:
            print("\n❌ Dispatch failed!")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
