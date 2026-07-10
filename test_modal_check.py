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

from app.repositories.agro_tanks_repository import AgroTanksRepository

with app.app_context():
    print("=== SPRAWDZAM MODAL 'SUROWCE W PRODUKCJI' ===\n")
    
    tanks_repo = AgroTanksRepository()
    
    # Check snapshot (what modal uses - show_empty=True to include 0kg items)
    print("1. Checking production_inventory_snapshot (show_empty=True):")
    snapshot = tanks_repo.get_production_inventory_snapshot(linia='AGRO', show_empty=True)
    print(f"   Found {len(snapshot) if snapshot else 0} items")
    if snapshot:
        for item in snapshot:
            if 'BB03' in str(item.get('zbiornik', '')):
                print(f"   ✓ FOUND BB03: Tank: {item.get('zbiornik')}, Nazwa: {item.get('nazwa')}, Stan: {item.get('stan_systemowy')}")
    
    # List all tanks
    print("\n2. All tanks in snapshot:")
    if snapshot:
        tanks_set = set()
        for item in snapshot:
            tank = item.get('zbiornik')
            if tank:
                tanks_set.add(tank)
        for tank in sorted(tanks_set):
            items_in_tank = [i for i in snapshot if i.get('zbiornik') == tank]
            print(f"   {tank}: {len(items_in_tank)} items")
    
    # Direct DB check
    print("\n3. Direct DB check - materiały w PRODUKCJA na BB03:")
    from app.db import get_db_connection
    from app.core.table_resolver import get_table_name
    
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    table_ruch = get_table_name('magazyn_ruch', 'AGRO')
    table_surowce = get_table_name('magazyn_surowce', 'AGRO')
    
    cur.execute(f"""
        SELECT r.id, r.surowiec_id, r.typ_ruchu, r.ilosc, r.zbiornik, r.status,
               s.nazwa, s.stan_magazynowy, s.lokalizacja
        FROM {table_ruch} r
        LEFT JOIN {table_surowce} s ON r.surowiec_id = s.id
        WHERE r.zbiornik = 'BB03'
        ORDER BY r.id DESC
        LIMIT 5
    """)
    
    rows = cur.fetchall()
    print(f"   Found {len(rows)} records for BB03:")
    for row in rows:
        print(f"   - SurID: {row['surowiec_id']}, Ilość: {row['ilosc']} kg, Nazwa: {row['nazwa']}, Status: {row['status']}")
    
    cur.close()
    conn.close()

