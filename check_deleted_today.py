#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź wszystkie usunięte plany na 2026-02-07"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Wszystkie usunięte plany na 2026-02-07
    sql = """
    SELECT id, data_planu, produkt, sekcja, status, is_deleted, deleted_at 
    FROM plan_produkcji 
    WHERE data_planu='2026-02-07' AND (is_deleted=1 OR is_deleted IS NOT NULL)
    ORDER BY id
    """
    cursor.execute(sql)
    results = cursor.fetchall()
    
    print("\n📋 USUNIĘTE PLANY na 2026-02-07:")
    print(f"Znaleziono rekordów: {len(results)}\n")
    for row in results:
        print(f"ID {row['id']}: {row['produkt']} (sekcja: {row['sekcja']}, is_deleted: {row['is_deleted']})")
    
    # Również sprawdzić zaplanowane
    sql2 = """
    SELECT id, data_planu, produkt, sekcja, status, is_deleted 
    FROM plan_produkcji 
    WHERE data_planu='2026-02-07' AND (is_deleted IS NULL OR is_deleted=0)
    ORDER BY id
    """
    cursor.execute(sql2)
    results2 = cursor.fetchall()
    
    print(f"\n📋 NOWE/ZAPLANOWANE plany na 2026-02-07:")
    print(f"Znaleziono rekordów: {len(results2)}\n")
    for row in results2:
        print(f"ID {row['id']}: {row['produkt']} (sekcja: {row['sekcja']}, status: {row['status']})")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
