#!/usr/bin/env python3
"""Delete all Workowanie orders with '_BUF' in nazwa_zlecenia - WITHOUT confirmation"""

import mysql.connector
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

try:
    # 1. Find all Workowanie with '_BUF' in nazwa_zlecenia
    cursor.execute("""
        SELECT id, data_planu, produkt, nazwa_zlecenia, tonaz, status 
        FROM plan_produkcji 
        WHERE sekcja = 'Workowanie' AND nazwa_zlecenia LIKE '%_BUF%'
        ORDER BY data_planu DESC
    """)
    
    plans = cursor.fetchall()
    plan_ids = [row[0] for row in plans]
    
    print(f"Usuwam {len(plan_ids)} Workowanie z '_BUF' w nazwie...")
    
    if not plan_ids:
        print("Brak Workowanie do usunięcia")
    else:
        # 2. Delete from palety_workowanie first (cascading)
        placeholders = ','.join(['%s'] * len(plan_ids))
        cursor.execute(f"DELETE FROM palety_workowanie WHERE plan_id IN ({placeholders})", plan_ids)
        deleted_palety = cursor.rowcount
        print(f"✓ Usunięto {deleted_palety} wierszy z palety_workowanie")
        
        # 3. Delete from plan_produkcji (main records)
        cursor.execute(f"DELETE FROM plan_produkcji WHERE id IN ({placeholders})", plan_ids)
        deleted_plans = cursor.rowcount
        print(f"✓ Usunięto {deleted_plans} Workowanie z plan_produkcji")
        
        conn.commit()
        print(f"\n✅ Permanentnie usunięte wszystkie {deleted_plans} BUF zlecenia!")
        
except Exception as e:
    conn.rollback()
    print(f"❌ BŁĄD: {e}")
    import traceback
    traceback.print_exc()
finally:
    conn.close()
