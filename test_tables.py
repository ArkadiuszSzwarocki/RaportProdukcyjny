#!/usr/bin/env python3
"""Find users table."""

import sys
sys.path.insert(0, '.')

from app.core.database import get_db_connection

conn = get_db_connection()
try:
    cursor = conn.cursor(dictionary=True)
    
    print("=== Tables in database ===\n")
    cursor.execute("SHOW TABLES")
    rows = cursor.fetchall()
    
    for row in rows:
        table_name = list(row.values())[0]
        print(f"  {table_name}")
    
finally:
    conn.close()
