#!/usr/bin/env python
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# FIX: Update buffer for plan 1350 to have correct tonaz_rzeczywisty
# We know plan 1262 had real_tonaz=1095, so Zasyp plan 1350 should have buffer tonaz=1095
cursor.execute("""
    UPDATE bufor 
    SET tonaz_rzeczywisty = 1095
    WHERE zasyp_id = 1350 AND DATE(data_planu) = '2026-03-05'
""")

rowcount = cursor.rowcount
conn.commit()

print(f"Updated {rowcount} buffer rows: zasyp_id=1350, tonaz_rzeczywisty=1095")

# Verify
cursor.execute("SELECT id, zasyp_id, tonaz_rzeczywisty FROM bufor WHERE zasyp_id = 1350")
row = cursor.fetchone()
print(f"Buffer after update: {row}")

cursor.close()
conn.close()
