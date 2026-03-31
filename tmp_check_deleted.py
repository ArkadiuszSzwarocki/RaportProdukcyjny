import sys
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_plan = get_table_name('plan_produkcji', 'PSD')
    
    # Check for Zasyp orders that are 'zakonczone' but might be flagged as deleted
    q = f"SELECT id, produkt, sekcja, status, is_deleted FROM {table_plan} WHERE DATE(data_planu)='2026-03-31' AND status='zakonczone' AND sekcja='Zasyp'"
    cursor.execute(q)
    rows = cursor.fetchall()
    
    print("FINISHED ZASYPY ON 31.03 (inclusive of potentially deleted):")
    for r in rows:
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
