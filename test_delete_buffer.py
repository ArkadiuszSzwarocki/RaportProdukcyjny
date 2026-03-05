#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test delete buffer instead of move"""

import sys
sys.path.insert(0, '.')

from app import create_app
from app.db import get_db_connection

# Create app context
app = create_app()

with app.app_context():
    # First, prepare test data - only if needed
    conn = get_db_connection()
    
    # Check current buffer state
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
    count_before_04 = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
    count_before_05 = cursor.fetchone()[0]
    cursor.close()
    
    print(f"PRZED OPERACJĄ:")
    print(f"  Bufor 04.03: {count_before_04} rekordów")
    print(f"  Bufor 05.03: {count_before_05} rekordów")
    
    # Now test the function
    from app.services.planning_service import PlanningService
    result = PlanningService.przenies_niezrealizowane('2026-03-04')
    
    print(f"\nRESULTAT FUNKCJI:")
    print(f"  Sukces: {result[0]}")
    print(f"  Wiadomość: {result[1]}")
    print(f"  Ilość: {result[2]}")
    
    # Check state after
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
    count_after_04 = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
    count_after_05 = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    
    print(f"\nPO OPERACJI:")
    print(f"  Bufor 04.03: {count_after_04} rekordów")
    print(f"  Bufor 05.03: {count_after_05} rekordów")
    
    print(f"\nWERYFIKACJA:")
    if count_after_04 == 0:
        print("  ✓ Bufor z 04.03 został USUNIĘTY")
    else:
        print(f"  ✗ Bufor z 04.03 JESZCZE ISTNIEJE ({count_after_04} rekordów)")
    
    if result[0]:
        print("  ✓ Funkcja zwróciła sukces")
    else:
        print("  ✗ Funkcja zwróciła błąd")
