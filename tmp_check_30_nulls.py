import sys
from datetime import date
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_plan = get_table_name('plan_produkcji', 'PSD')
    
    q = f"SELECT id, produkt, sekcja, status, real_stop FROM {table_plan} WHERE DATE(data_planu)='2026-03-30' AND status='zakonczone' AND sekcja='Zasyp' AND real_stop IS NULL"
    cursor.execute(q)
    rows = cursor.fetchall()
    
    print("FINISHED ZASYPY ON 30.03 WITH NULL REAL_STOP:")
    for r in rows:
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
