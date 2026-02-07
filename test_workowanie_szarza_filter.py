#!/usr/bin/env python
"""
Test: Workowanie shows only plans that have szarża with status='zarejestowana'
"""
import sys
import os
from datetime import date, datetime
from app.db import get_db_connection, setup_database

# Setup
sys.path.insert(0, os.path.dirname(__file__))

def test_workowanie_szarza_filter():
    """Test that Workowanie filters plans by szarża presence"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Setup: Create test data
    test_date = date.today()
    
    # 1. Create two Zasyp plans
    cursor.execute("""
        INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, typ_produkcji)
        VALUES (%s, 'Zasyp', 'TestCukier1', 100, 'zaplanowane', 'worki_zgrzewane_25')
    """, (test_date,))
    zasyp_plan_id_1 = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, typ_produkcji)
        VALUES (%s, 'Zasyp', 'TestCukier2', 100, 'zaplanowane', 'worki_zgrzewane_25')
    """, (test_date,))
    zasyp_plan_id_2 = cursor.lastrowid
    
    # 2. Create three Workowanie plans (same products)
    cursor.execute("""
        INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, typ_produkcji)
        VALUES (%s, 'Workowanie', 'TestCukier1', 100, 'zaplanowane', 'worki_zgrzewane_25')
    """, (test_date,))
    work_plan_id_1 = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, typ_produkcji)
        VALUES (%s, 'Workowanie', 'TestCukier2', 100, 'zaplanowane', 'worki_zgrzewane_25')
    """, (test_date,))
    work_plan_id_2 = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, typ_produkcji)
        VALUES (%s, 'Workowanie', 'TestCukier3', 100, 'zaplanowane', 'worki_zgrzewane_25')
    """, (test_date,))
    work_plan_id_3 = cursor.lastrowid
    
    # 3. Add szarża ONLY for Zasyp plan 1 (ze statusem 'zarejestowana')
    cursor.execute("""
        INSERT INTO szarze (plan_id, waga, data_dodania, godzina, status)
        VALUES (%s, 50, NOW(), '14:00:00', 'zarejestowana')
    """, (zasyp_plan_id_1,))
    
    conn.commit()
    
    # Test: Query Workowanie with filter
    cursor.execute("""
        SELECT DISTINCT p.id, p.produkt
        FROM plan_produkcji p
        WHERE DATE(p.data_planu) = %s AND LOWER(p.sekcja) = LOWER('Workowanie') 
          AND p.status != 'nieoplacone' AND p.is_deleted = 0 
          AND EXISTS (
            SELECT 1 FROM szarze s
            INNER JOIN plan_produkcji pr ON s.plan_id = pr.id
            WHERE s.status = 'zarejestowana'
              AND DATE(s.data_dodania) = DATE(p.data_planu)
              AND pr.produkt = p.produkt
          )
        ORDER BY p.id ASC
    """, (test_date,))
    result = cursor.fetchall()
    
    print(f"📋 Test: Workowanie szarża filter")
    print(f"Test date: {test_date}")
    print(f"\nCreated data:")
    print(f"  Zasyp plan 1: id={zasyp_plan_id_1}, produkt=TestCukier1 ✓ (has szarża)")
    print(f"  Zasyp plan 2: id={zasyp_plan_id_2}, produkt=TestCukier2 ✗ (no szarża)")
    print(f"  Workowanie plan 1: id={work_plan_id_1}, produkt=TestCukier1 (matches Zasyp plan 1)")
    print(f"  Workowanie plan 2: id={work_plan_id_2}, produkt=TestCukier2 (matches Zasyp plan 2)")
    print(f"  Workowanie plan 3: id={work_plan_id_3}, produkt=TestCukier3 (no match)")
    
    print(f"\n🔍 Filtered Workowanie plans (should show ONLY TestCukier1):")
    print(f"  Result count: {len(result)}")
    
    if len(result) == 1 and result[0][1] == 'TestCukier1':
        print(f"  ✅ PASS: Found only TestCukier1 (id={result[0][0]})")
    else:
        print(f"  ❌ FAIL: Expected 1 plan (TestCukier1), got {len(result)}:")
        for row in result:
            print(f"    - id={row[0]}, produkt={row[1]}")
        return False
    
    # Cleanup
    cursor.execute("DELETE FROM szarze WHERE plan_id = %s", (zasyp_plan_id_1,))
    cursor.execute("DELETE FROM plan_produkcji WHERE id IN (%s, %s, %s, %s, %s)", 
                   (zasyp_plan_id_1, zasyp_plan_id_2, work_plan_id_1, work_plan_id_2, work_plan_id_3))
    conn.commit()
    conn.close()
    
    print("\n✅ Test passed!")
    return True

if __name__ == '__main__':
    try:
        setup_database()
        success = test_workowanie_szarza_filter()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
