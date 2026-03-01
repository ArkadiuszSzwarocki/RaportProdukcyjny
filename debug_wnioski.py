#!/usr/bin/env python
"""Debug script to check pending wnioski in database."""
import sys

try:
    from app.db import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Count pending
    cursor.execute("SELECT COUNT(*) FROM wnioski_wolne WHERE status='pending'")
    count = cursor.fetchone()
    print(f"[DB] Pending wnioski count: {count[0]}")
    
    # Fetch some
    cursor.execute("""
        SELECT w.id, p.imie_nazwisko, w.typ, w.data_od, w.status 
        FROM wnioski_wolne w 
        JOIN pracownicy p ON w.pracownik_id = p.id 
        WHERE w.status='pending' 
        LIMIT 5
    """)
    rows = cursor.fetchall()
    
    if rows:
        for row in rows:
            print(f"[DB] ID={row[0]}, pracownik={row[1]}, typ={row[2]}, data={row[3]}, status={row[4]}")
    else:
        print("[DB] NO PENDING WNIOSKI FOUND")
    
    # Check schema
    cursor.execute("DESCRIBE wnioski_wolne")
    cols = cursor.fetchall()
    print(f"\n[SCHEMA] wnioski_wolne columns: {[col[0] for col in cols]}")
    
    conn.close()
    
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()
