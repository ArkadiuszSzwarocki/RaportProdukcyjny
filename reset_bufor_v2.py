#!/usr/bin/env python
"""Reset buffer to 2026-03-04 for clean test"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Reset buffer and plan records to 2026-03-04
cursor.execute("UPDATE bufor SET data_planu = '2026-03-04' WHERE zasyp_id = 1262")
print(f"Buffer reset: {cursor.rowcount} records")

# Delete newly created plans from test
cursor.execute("DELETE FROM plan_produkcji WHERE id IN (1287, 1288)")
print(f"Plans deleted: {cursor.rowcount} records")

conn.commit()
conn.close()

print("✓ Reset complete - ready for next test")
