import json
from datetime import date, datetime
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_plan = get_table_name('plan_produkcji', 'PSD')
    
    q = f"SELECT id, produkt, sekcja, status, real_start, real_stop FROM {table_plan} WHERE DATE(data_planu)='2026-03-31' ORDER BY sekcja, id"
    cursor.execute(q)
    rows = cursor.fetchall()
    
    for r in rows:
        for k, v in r.items():
            if isinstance(v, (datetime, date)):
                r[k] = str(v)
                
    with open('out_all_31.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
