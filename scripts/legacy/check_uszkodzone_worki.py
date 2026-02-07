#!/usr/bin/env python
# -*- coding: utf-8 -*-
from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute('SHOW COLUMNS FROM plan_produkcji LIKE "uszkodzone_worki"')
r = cursor.fetchone()

if r:
    print("✓ Kolumna 'uszkodzone_worki' już istnieje w bazie")
else:
    print("✗ Kolumna 'uszkodzone_worki' nie istnieje - dodaję nową...")
    cursor.execute('ALTER TABLE plan_produkcji ADD COLUMN uszkodzone_worki INT DEFAULT 0')
    conn.commit()
    print("✓ Dodano kolumnę 'uszkodzone_worki'")

conn.close()
