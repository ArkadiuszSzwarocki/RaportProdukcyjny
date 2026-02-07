#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root')
sys.path.insert(0, 'c:/Users/arkad/Documents/GitHub/RaportProdukcyjny')

from app.db import get_db_connection
from datetime import date, datetime

# Add test plan
conn = get_db_connection()
cursor = conn.cursor()

insert_sql = """
INSERT INTO plan_produkcji 
(produkt, tonaz, sekcja, data_planu, typ_produkcji, status, kolejnosc, is_deleted)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""

cursor.execute(insert_sql, (
    "Test Plan", 
    1000, 
    "Zasyp",
    date.today(),
    "standard",
    "zaplanowane",
    1,
    0  # not deleted
))

conn.commit()
last_id = cursor.lastrowid
conn.close()

print(f"[OK] Created test plan with ID: {last_id}")
