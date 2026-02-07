#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprawdź co endpoint get_deleted_plans zwraca"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import get_db_connection

def main():
    date_str = '2026-02-07'
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Dokładnie to samo co endpoint
    sql = "SELECT id, produkt, tonaz, status, deleted_at FROM plan_produkcji WHERE DATE(data_planu) = %s AND is_deleted = 1 ORDER BY deleted_at DESC"
    cursor.execute(sql, (date_str,))
    results = cursor.fetchall()
    
    print(f"\n📡 Endpoint /api/get_deleted_plans/{date_str} zwraca:")
    print(f"Znaleziono rekordów: {len(results)}\n")
    for row in results:
        print(f"ID {row['id']}: {row['produkt']} | tonaz: {row['tonaz']} | status: {row['status']}")
        print(f"  deleted_at: {row['deleted_at']}")
        
        # Sprawdź sekcję dla każdego planu
        cursor.execute("SELECT sekcja FROM plan_produkcji WHERE id = %s", (row['id'],))
        sekcja_res = cursor.fetchone()
        if sekcja_res:
            print(f"  ⚠️  sekcja: '{sekcja_res['sekcja']}'")
    
    # Czy plan 475 jest?
    cursor.execute("SELECT id, produkt, is_deleted, sekcja FROM plan_produkcji WHERE id = 475")
    plan475 = cursor.fetchone()
    if plan475:
        print(f"\n✅ Plan ID 475 w bazie: {plan475['produkt']}")
        print(f"   is_deleted: {plan475['is_deleted']}")
        print(f"   sekcja: {plan475['sekcja']}")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
