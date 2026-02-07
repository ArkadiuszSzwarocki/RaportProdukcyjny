#!/usr/bin/env python3
"""
Verify dashboard shows correct realization (3120 kg) for plan 399
"""
import sys
sys.path.insert(0, '.')

from db import get_db_connection

def verify_plan_399():
    """Check that plan 399 has tonaz_rzeczywisty = 3120"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check plan 399 tonaz_rzeczywisty in DB
    cursor.execute("""
        SELECT id, produkt, tonaz, tonaz_rzeczywisty, status, sekcja 
        FROM plan_produkcji 
        WHERE id = 399
    """)
    plan = cursor.fetchone()
    
    if not plan:
        print("❌ Plan 399 not found in database")
        return False
    
    plan_id, produkt, tonaz, tonaz_rzeczywisty, status, sekcja = plan
    print(f"Plan 399 DB State:")
    print(f"  Produkt: {produkt}")
    print(f"  Tonaz (planned): {tonaz} kg")
    print(f"  Tonaz rzeczywisty (DB): {tonaz_rzeczywisty} kg")
    print(f"  Status: {status}")
    print(f"  Sekcja: {sekcja}")
    
    # Check szarze for this plan
    cursor.execute("""
        SELECT SUM(waga) as total_waga, COUNT(*) as count 
        FROM szarze 
        WHERE plan_id = %s
    """, (399,))
    szarze_result = cursor.fetchone()
    szarze_sum = szarze_result[0] if szarze_result and szarze_result[0] else 0
    szarze_count = szarze_result[1] if szarze_result else 0
    
    print(f"\nSzarze for plan 399:")
    print(f"  Count: {szarze_count}")
    print(f"  Sum of weights: {szarze_sum} kg")
    
    # Detailed szarze entries
    cursor.execute("""
        SELECT id, waga, data_dodania 
        FROM szarze 
        WHERE plan_id = %s 
        ORDER BY id DESC
    """, (399,))
    szarze_entries = cursor.fetchall()
    if szarze_entries:
        print(f"\n  Szarze entries (last 10):")
        for sz_id, waga, data_dodania in szarze_entries[:10]:
            print(f"    ID {sz_id}: {waga} kg (added {data_dodania})")
    
    cursor.close()
    conn.close()
    
    # Verify: tonaz_rzeczywisty should equal szarze sum
    if szarze_sum > 0 and tonaz_rzeczywisty != szarze_sum:
        print(f"\n⚠️  MISMATCH: DB tonaz_rzeczywisty ({tonaz_rzeczywisty}) != szarze sum ({szarze_sum})")
        return False
    
    if tonaz_rzeczywisty == 3120:
        print(f"\n✓ Correct! tonaz_rzeczywisty = {tonaz_rzeczywisty} kg (expected 3×1040 = 3120 kg)")
        return True
    else:
        print(f"\n❌ ERROR: tonaz_rzeczywisty = {tonaz_rzeczywisty} kg (expected 3120 kg)")
        return False

if __name__ == '__main__':
    success = verify_plan_399()
    sys.exit(0 if success else 1)
