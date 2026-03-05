#!/usr/bin/env python
"""Test przenies_niezrealizowane with full diagnostics"""
import sys
sys.path.insert(0, '.')

from app.core.factory import create_app
app = create_app()

with app.app_context():
    from app.db import get_db_connection
    from app.services.planning_service import PlanningService
    
    # First check what's actually in buffer
    print("=== PRZED OPERACJĄ ===")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-04',))
    count_04_before = cursor.fetchone()['cnt']
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-05',))
    count_05_before = cursor.fetchone()['cnt']
    
    print(f"Buffer na 04.03: {count_04_before} rekordów")
    print(f"Buffer na 05.03: {count_05_before} rekordów")
    
    # Sprawdź szczegóły
    cursor.execute('SELECT id, zasyp_id, produkt, data_planu FROM bufor WHERE zasyp_id = 1262 OR zasyp_id IS NULL LIMIT 3')
    rows = cursor.fetchall()
    print("\nSzczegóły buforu:")
    for row in rows:
        print(f"  ID={row['id']}, zasyp_id={row['zasyp_id']}, produkt={row['produkt']}, data={row['data_planu']}")
    
    cursor.close()
    conn.close()
    
    # Test operator
    print("\n=== OPERACJA ===")
    success, message, count = PlanningService.przenies_niezrealizowane('2026-03-04')
    
    print(f"Success: {success}")
    print(f"Message: {message }")
    print(f"Count: {count}")
    
    # Check after
    print("\n=== PO OPERACJI ===")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-04',))
    count_04_after = cursor.fetchone()['cnt']
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-05',))
    count_05_after = cursor.fetchone()['cnt']
    
    print(f"Buffer na 04.03: {count_04_after} rekordów (było {count_04_before})")
    print(f"Buffer na 05.03: {count_05_after} rekordów (było {count_05_before})")
    
    # Status check
    if count_05_after > count_05_before:
        print("✅ SUKCES - Buffer przeniesiony!")
    else:
        print("❌ BŁĄD - Buffer nie przeniósł się")
    
    # Szczegóły
    print("\nSzczegóły buforu PO:")
    cursor.execute('SELECT id, zasyp_id, produkt, data_planu FROM bufor WHERE zasyp_id = 1262 OR zasyp_id IS NULL LIMIT 3')
    rows = cursor.fetchall()
    for row in rows:
        print(f"  ID={row['id']}, zasyp_id={row['zasyp_id']}, produkt={row['produkt']}, data={row['data_planu']}")
    
    cursor.close()
    conn.close()
    
    # Check plans created
    print("\n=== NOWE PLANY ===")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT COUNT(*) as cnt FROM plan_produkcji WHERE DATE(data_planu) = %s', ('2026-03-05',))
    new_plans_count = cursor.fetchone()['cnt']
    print(f"Nowe plany na 05.03: {new_plans_count}")
    
    cursor.close()
    conn.close()
