#!/usr/bin/env python3
"""Find valid login credentials."""

import sys
sys.path.insert(0, '.')

from app.core.database import get_db_connection

conn = get_db_connection()
try:
    cursor = conn.cursor(dictionary=True)
    
    print("=== Available users ===\n")
    cursor.execute("SELECT id, login, rola FROM uzytkownicy LIMIT 10")
    rows = cursor.fetchall()
    
    for row in rows:
        print(f"ID: {row.get('id')}, Login: {row.get('login')}, Role: {row.get('rola')}")
    
finally:
    conn.close()
