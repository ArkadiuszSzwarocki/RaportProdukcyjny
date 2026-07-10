#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'a:\\GitHub\\RaportProdukcyjny')

from app.db import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # Search by partial match (maybe it's part of the SSCC)
    pattern = '%080520268225338153%'
    print(f"=== SZUKAM Like '{pattern}' ===\n")
    
    # Check magazyn_surowce nr_palety or inne pola
    cur.execute("""
        SELECT id, nr_palety, nazwa, stan_magazynowy, lokalizacja 
        FROM magazyn_surowce 
        WHERE nr_palety LIKE %s OR id LIKE %s
    """, (pattern, pattern))
    rows = cur.fetchall()
    
    if rows:
        print("✓ Znaleziono w magazyn_surowce:")
        for r in rows:
            print(f"  ID: {r['id']}, Paleta: {r['nr_palety']}, Nazwa: {r['nazwa']}, Stan: {r['stan_magazynowy']}, Lokalizacja: {r['lokalizacja']}")
    else:
        print("✗ Nie znaleziono w magazyn_surowce\n")
    
    # Check magazyn_ruch
    cur.execute("""
        SELECT * FROM magazyn_ruch 
        WHERE surowiec_id LIKE %s
        LIMIT 3
    """, (pattern,))
    rows = cur.fetchall()
    
    if rows:
        print("✓ Znaleziono w magazyn_ruch:")
        for r in rows:
            print(f"  {r}")
    else:
        print("✗ Nie znaleziono w magazyn_ruch")
    
    # List ALL surowce with 'SUR' like codes starting with last digits
    print("\n=== SZUKAM KODÓW Starting WITH 'SUR0805' ===")
    cur.execute("""
        SELECT id, nr_palety, nazwa, stan_magazynowy
        FROM magazyn_surowce
        WHERE id LIKE 'SUR0805%' OR nr_palety LIKE 'SUR0805%'
        LIMIT 10
    """)
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  {r['id']} | Paleta: {r['nr_palety']} | {r['nazwa']} | {r['stan_magazynowy']} kg")
    else:
        print("  (brak)")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
