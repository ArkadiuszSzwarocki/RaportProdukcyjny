#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'a:\\GitHub\\RaportProdukcyjny')

from app.db import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # First let's check WHERE is this surowiec
    print("=== SZUKAM SUR080520268225338153 ===")
    
    # Check all tables with surowiec_id or id
    cur.execute("SHOW TABLES")
    tables = cur.fetchall()
    
    surowiec_id = 'SUR080520268225338153'
    found_in = []
    
    for table_row in tables:
        table_name = table_row[list(table_row.keys())[0]]
        # Skip system tables
        if 'information' in table_name or 'performance' in table_name:
            continue
        try:
            # Check if surowiec_id column exists
            cur.execute(f"DESCRIBE {table_name}")
            cols = cur.fetchall()
            has_surowiec_id = any(c['Field'] == 'surowiec_id' for c in cols)
            has_id = any(c['Field'] == 'id' for c in cols)
            
            if has_surowiec_id:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE surowiec_id = %s", (surowiec_id,))
                count = cur.fetchone()['cnt']
                if count > 0:
                    found_in.append(f"{table_name} (surowiec_id): {count} rows")
            
            if has_id and 'magazyn' in table_name:
                cur.execute(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE id = %s", (surowiec_id,))
                count = cur.fetchone()['cnt']
                if count > 0:
                    found_in.append(f"{table_name} (id): {count} rows")
        except:
            pass
    
    if found_in:
        print("✓ Znaleziono w:")
        for location in found_in:
            print(f"  - {location}")
    else:
        print("✗ Surowiec nie znaleziony nigdzie!")
    
    # Check last moves in magazyn_ruch
    print("\n=== OSTATNIE RUCHY MAGAZYN_RUCH ===")
    cur.execute("""
        SELECT id, typ_ruchu, ilosc, zbiornik, status, autor_data 
        FROM magazyn_ruch 
        WHERE surowiec_id = %s
        ORDER BY id DESC 
        LIMIT 5
    """, (surowiec_id,))
    rows = cur.fetchall()
    if rows:
        for i, r in enumerate(rows, 1):
            print(f"\n{i}. {r['typ_ruchu']} | {r['ilosc']} kg | zbiornik: {r['zbiornik']} | status: {r['status']} | {r['autor_data']}")
    else:
        print("✗ Brak ruchów w magazyn_ruch")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
