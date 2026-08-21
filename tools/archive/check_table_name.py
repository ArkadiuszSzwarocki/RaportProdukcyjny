#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sprawdza nazwę tabeli dla magazyn_ruch w AGRO.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_table_name, get_db_connection

def check_table():
    linia = 'AGRO'
    
    print("=" * 80)
    print("SPRAWDZANIE NAZWY TABELI")
    print("=" * 80)
    
    table_ruch = get_table_name('magazyn_ruch', linia)
    print(f"\nget_table_name('magazyn_ruch', '{linia}') = '{table_ruch}'")
    
    # Sprawdź czy tabela istnieje
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"SHOW TABLES LIKE '{table_ruch}'")
        result = cursor.fetchone()
        if result:
            print(f"✓ Tabela '{table_ruch}' ISTNIEJE")
        else:
            print(f"✗ Tabela '{table_ruch}' NIE ISTNIEJE!")
            
        # Sprawdź wszystkie tabele magazyn_ruch*
        cursor.execute("SHOW TABLES LIKE 'magazyn_ruch%'")
        tables = cursor.fetchall()
        print(f"\nWszystkie tabele magazyn_ruch*:")
        for t in tables:
            print(f"  - {t[0]}")
            
    finally:
        cursor.close()
        conn.close()
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    check_table()
