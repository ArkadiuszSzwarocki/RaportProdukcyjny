#!/usr/bin/env python3
"""Check if plan ID 900 has real_stop recorded"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdź plan ID 900
cursor.execute("""
    SELECT id, sekcja, produkt, tonaz, status, real_start, real_stop, 
           tonaz_rzeczywisty, zasyp_id
    FROM plan_produkcji
    WHERE id = 900
""")

result = cursor.fetchone()
if result:
    id, sekcja, produkt, tonaz, status, real_start, real_stop, tonaz_rz, zasyp_id = result
    print(f"✅ Plan ID 900 znaleziony:")
    print(f"  - Sekcja: {sekcja}")
    print(f"  - Produkt: {produkt}")
    print(f"  - Tonaz: {tonaz} kg")
    print(f"  - Status: {status}")
    print(f"  - Real Start: {real_start}")
    print(f"  - Real Stop: {real_stop} ⚠️ {'(JEST)' if real_stop else '(BRAK!)'}")
    print(f"  - Tonaz Rzeczywisty: {tonaz_rz}")
    print(f"  - Zasyp ID: {zasyp_id}")
    print()
    
    if real_stop is None:
        print("❌ PROBLEM: real_stop = NULL (STOP nie został zapisany)")
        print()
        print("🔧 Naprawianie:")
        cursor.execute("""
            UPDATE plan_produkcji
            SET status='zakonczone', real_stop=NOW()
            WHERE id = 900
        """)
        conn.commit()
        print("✅ Zaktualizowano: status='zakonczone', real_stop=NOW()")
    else:
        print("✅ OK: real_stop jest zapisany")
else:
    print("❌ Plan ID 900 nie znaleziony!")

conn.close()
