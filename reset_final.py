#!/usr/bin/env python
"""Reset buffer and plans for clean test"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Reset buffer from ANY date back to 04.03
cursor.execute("UPDATE bufor SET data_planu = '2026-03-04' WHERE zasyp_id = 1262")
reset_count = cursor.rowcount

# Delete test plans
cursor.execute("DELETE FROM plan_produkcji WHERE id >= 1289")
delete_count = cursor.rowcount

conn.commit()
conn.close()

print(f"✓ Buffer reset: {reset_count} records")
print(f"✓ Plans deleted: {delete_count} records")
