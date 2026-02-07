#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź czy plan 2222222222 ma is_deleted=1"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import get_db_connection

def main():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Szukaj planu 2222222222
    sql = "SELECT id, data_planu, produkt, sekcja, status, is_deleted, deleted_at FROM plan_produkcji WHERE produkt='2222222222' LIMIT 5"
    cursor.execute(sql)
    results = cursor.fetchall()
    
    print("\n📋 PLAN 2222222222 w bazie:")
    print(f"Znaleziono rekordów: {len(results)}")
    for row in results:
        print(f"\n  ID: {row['id']}")
        print(f"  Data: {row['data_planu']}")
        print(f"  Produkt: {row['produkt']}")
        print(f"  Sekcja: {row['sekcja']}")
        print(f"  Status: {row['status']}")
        print(f"  is_deleted: {row['is_deleted']}")
        print(f"  deleted_at: {row['deleted_at']}")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
