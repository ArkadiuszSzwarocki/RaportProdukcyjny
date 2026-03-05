#!/usr/bin/env python
import sys
import os
sys.path.insert(0, os.getcwd())

# Import app properly
from app.core.factory import create_app
from app.db import get_db_connection
from app.services.planning_service import PlanningService

app = create_app()

with app.app_context():
    # Check state before
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
    before_04 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
    before_05 = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"STAN PRZED:")
    print(f"  04.03: {before_04} rekordów")
    print(f"  05.03: {before_05} rekordów")
    
    # Call function
    print("\nWYKONYWANIE FUNKCJI...")
    success, message, count = PlanningService.przenies_niezrealizowane('2026-03-04')
    
    print(f"\nWYNIK FUNKCJI:")
    print(f"  Sukces: {success}")
    print(f"  Wiadomość: {message}")
    print(f"  Ilość: {count}")
    
    # Check state after
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
    after_04 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
    after_05 = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"\nSTAN PO:")
    print(f"  04.03: {after_04} rekordów")
    print(f"  05.03: {after_05} rekordów")
    
    print(f"\nWERYFIKACJA:")
    if after_04 == 0 and before_04 == 1:
        print("  ✓ Bufor z 04.03 USUNIĘTY (1 → 0)")
    elif after_04 == before_04:
        print(f"  ✗ Bufor z 04.03 NIE zmienił się ({before_04} → {after_04})")
    else:
        print(f"  ? Bufor z 04.03 zmienił się ({before_04} → {after_04})")
    
    if after_05 > before_05:
        print(f"  ✓ Bufora na 05.03 dodane ({before_05} → {after_05})")
    else:
        print(f"  ? Bufor na 05.03 nie zmienił się ({before_05} → {after_05})")
