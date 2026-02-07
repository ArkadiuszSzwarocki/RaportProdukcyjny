#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź strukturę tabeli plan_produkcji"""

import sys
import io
from db import get_db_connection

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = get_db_connection()
cursor = conn.cursor()

print("\nKOLUMNY W plan_produkcji:")
cursor.execute("DESCRIBE plan_produkcji")
for col in cursor.fetchall():
    print(f"  - {col}")

print("\n\nWszystkie Workowania dzisiaj:")
from datetime import date
dzisiaj = str(date.today())

cursor.execute("""
    SELECT *
    FROM plan_produkcji
    WHERE data_planu = %s AND sekcja = 'Workowanie'
    LIMIT 1
""", (dzisiaj,))

row = cursor.fetchone()
if row:
    cursor.execute("DESCRIBE plan_produkcji")
    cols = [c[0] for c in cursor.fetchall()]
    print(f"Znaleziono {len(row)} kolumn")
    print(f"\nPierwsze Workowanie: {dict(zip(cols[:len(row)], row))}")
else:
    print("❌ BEZ WORKOWANIA!")

conn.close()
