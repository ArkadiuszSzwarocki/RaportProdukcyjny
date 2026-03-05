#!/usr/bin/env python
"""Check buffer state and reset properly"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Check where is the record
cursor.execute('SELECT DATE(data_planu) as data FROM bufor WHERE zasyp_id = 1262 LIMIT 1')
row = cursor.fetchone()
if row:
    print(f"Record is currently on: {row['data']}")
else:
    print("No record found for zasyp_id 1262")

cursor.close()
conn.close()
