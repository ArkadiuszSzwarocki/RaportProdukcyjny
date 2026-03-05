#!/usr/bin/env python
"""Direct test of przenies_niezrealizowane function with the fixed logic"""
import sys
sys.path.insert(0, '.')

# Set Flask app context
from app.core.factory import create_app
app = create_app()

with app.app_context():
    from app.services.planning_service import PlanningService
    from datetime import datetime, timedelta
    
    print("=== TESTING PlanningService.przenies_niezrealizowane ===\n")
    
    try:
        result = PlanningService.przenies_niezrealizowane(
            current_data='2026-03-04'
        )
        
        print(f"Result tuple: {result}")
        print(f"Length: {len(result)}")
        
        if len(result) == 3:
            success, message, count = result
            print(f"\n[Result] Success={success}")
            print(f"[Message] {message}")
            print(f"[Count] {count} plans created\n")
        elif len(result) == 2:
            success, message = result
            print(f"\n[Result] Success={success}")
            print(f"[Message] {message}\n")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Check buffer
    from app.db import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    print("=== CHECKING BUFFER AFTER OPERATION ===")
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-04',))
    count_04 = cursor.fetchone()['cnt']
    
    cursor.execute('SELECT COUNT(*) as cnt FROM bufor WHERE DATE(data_planu) = %s', ('2026-03-05',))
    count_05 = cursor.fetchone()['cnt']
    
    print(f"Buffer on 04.03: {count_04} records")
    print(f"Buffer on 05.03: {count_05} records ✓" if count_05 > 0 else f"Buffer on 05.03: {count_05} records ❌")
    
    cursor.close()
    conn.close()
