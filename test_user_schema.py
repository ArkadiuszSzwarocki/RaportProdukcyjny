#!/usr/bin/env python3
"""Check users table structure."""

import sys
sys.path.insert(0, '.')

from app.core.database import get_db_connection

conn = get_db_connection()
try:
    cursor = conn.cursor(dictionary=True)
    
    print("=== Users table structure ===\n")
    cursor.execute("DESCRIBE uzytkownicy")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"  {row.get('Field')}: {row.get('Type')} ({row.get('Null')})")
    
    print("\n=== Sample user data ===\n")
    cursor.execute("SELECT login, rola FROM uzytkownicy LIMIT 3")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"  {row.get('login')} ({row.get('rola')})")
    
finally:
    conn.close()
