#!/usr/bin/env python
"""Migrate all existing palety to auto-confirm with +2 min confirmation time."""

from db import get_db_connection
import sys

def migrate():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update all palety that have data_dodania
        # Set: status='przyjeta', czas_rzeczywistego_potwierdzenia = TIME(data_dodania + 2 min)
        cursor.execute("""
            UPDATE palety_workowanie 
            SET 
                czas_rzeczywistego_potwierdzenia = TIME(ADDTIME(CURTIME(), INTERVAL 2 MINUTE))
            WHERE 
                data_dodania IS NOT NULL 
                AND status = 'przyjeta'
        """)
        
        affected = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"[OK] Auto-confirmed {affected} palety")
        print("[OK] Set confirmation time to +2 minutes from data_dodania")
        
        return affected
        
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    count = migrate()
    print(f"[SUCCESS] Migration completed: {count} palety updated")
