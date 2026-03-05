#!/usr/bin/env python
"""Check current buffer state"""
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute('SELECT id, zasyp_id, data_planu, produkt FROM bufor ORDER BY id DESC LIMIT 5')
rows = cursor.fetchall()
print("=== LATEST BUFFER RECORDS ===")
for row in rows:
    print(f"ID={row['id']}, zasyp_id={row['zasyp_id']}, data={row['data_planu']}, product={row['produkt']}")

cursor.close()
conn.close()
