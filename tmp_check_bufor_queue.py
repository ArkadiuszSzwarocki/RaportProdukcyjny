import sys
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_bufor = get_table_name('bufor', 'PSD')
    
    q = f"SELECT id, produkt, status, data_planu, kolejka FROM {table_bufor} WHERE DATE(data_planu)='2026-03-31' AND status='aktywny' ORDER BY kolejka ASC"
    cursor.execute(q)
    rows = cursor.fetchall()
    
    print("ACTIVE BUFOR ENTRIES FOR 31.03:")
    for r in rows:
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
