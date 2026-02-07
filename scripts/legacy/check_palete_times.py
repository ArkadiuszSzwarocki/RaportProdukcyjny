#!/usr/bin/env python
"""Check palete confirmation times."""

from db import get_db_connection
import sys

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check palete for today
    cursor.execute("""
        SELECT pw.id, p.produkt, pw.data_dodania, pw.czas_rzeczywistego_potwierdzenia, pw.status 
        FROM palety_workowanie pw
        JOIN plan_produkcji p ON pw.plan_id = p.id
        WHERE DATE(pw.data_dodania) = CURDATE() 
        ORDER BY pw.id DESC 
        LIMIT 10
    """)
    
    rows = cursor.fetchall()
    print(f"[INFO] Found {len(rows)} palety for today")
    print()
    print("ID | Produkt | Data Dodania | Czas Rzeczywisty | Status")
    print("---|---------|--------------|------------------|-------")
    for row in rows:
        id_val, prod, data_dod, czas_rzecz, status = row
        data_str = str(data_dod)[-8:] if data_dod else "-"
        czas_str = str(czas_rzecz) if czas_rzecz else "-"
        print(f"{id_val:3d} | {prod:20s} | {data_str:12s} | {czas_str:16s} | {status}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
