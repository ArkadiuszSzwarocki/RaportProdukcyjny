import json
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_plan = get_table_name('plan_produkcji', 'PSD')
    
    # Check for Zasyp orders that are 'zakonczone' but have NULL real_stop
    # or Workowanie orders that are stuck 
    q = f"""
        SELECT id, produkt, sekcja, status, data_planu, real_stop 
        FROM {table_plan} 
        WHERE status='zakonczone' AND sekcja='Zasyp' AND real_stop IS NULL
    """
    cursor.execute(q)
    null_stops = cursor.fetchall()
    
    print("ZASYPY WITH NULL REAL_STOP:")
    for r in null_stops:
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
