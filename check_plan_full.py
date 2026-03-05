#!/usr/bin/env python
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

# Check plan 1350
cursor.execute("SELECT * FROM plan_produkcji WHERE id=1350")
plan_1350 = cursor.fetchone()
print("Plan 1350:", plan_1350)

# Check original plan 1262
cursor.execute("SELECT * FROM plan_produkcji WHERE id=1262")
plan_1262 = cursor.fetchone()
print("\nPlan 1262:", plan_1262)

# Also check what's in bufor linked to 1350
cursor.execute("SELECT * FROM bufor WHERE zasyp_id=1350")
bufor_1350 = cursor.fetchone()
print("\nBuffer for zasyp_id=1350:", bufor_1350)

cursor.close()
conn.close()
