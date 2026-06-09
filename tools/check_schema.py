#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sprawdza schemat tabeli magazyn_surowce."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

print("\n" + "="*80)
print("SCHEMAT TABELI: magazyn_surowce")
print("="*80 + "\n")

cursor.execute("DESCRIBE magazyn_surowce")
columns = cursor.fetchall()

for col in columns:
    print(f"{col[0]:30} | {col[1]:20} | NULL: {col[2]:3} | Key: {col[3]:3} | Default: {str(col[4]):10}")

print("\n" + "="*80)
print("SCHEMAT TABELI: palety_historia")
print("="*80 + "\n")

cursor.execute("DESCRIBE palety_historia")
columns = cursor.fetchall()

for col in columns:
    print(f"{col[0]:30} | {col[1]:20} | NULL: {col[2]:3} | Key: {col[3]:3} | Default: {str(col[4]):10}")

conn.close()
