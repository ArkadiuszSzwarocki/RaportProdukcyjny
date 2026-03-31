import sys
from datetime import date
try:
    from app.db import get_db_connection, get_table_name
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table_plan = get_table_name('plan_produkcji', 'PSD')
    
    # Check Zasyp orders for 31.03 that are finished
    q_zasyp = f"SELECT id, produkt, status, real_stop FROM {table_plan} WHERE DATE(data_planu)='2026-03-31' AND sekcja='Zasyp' AND status='zakonczone' ORDER BY real_stop ASC"
    cursor.execute(q_zasyp)
    zasypy = cursor.fetchall()
    
    # Check Workowanie orders for 31.03
    q_work = f"SELECT id, produkt, status FROM {table_plan} WHERE DATE(data_planu)='2026-03-31' AND sekcja='Workowanie' ORDER BY id ASC"
    cursor.execute(q_work)
    worki = cursor.fetchall()
    
    print("FINISHED ZASYPY:")
    for z in zasypy:
        print(f"ID:{z['id']} | Prod:{z['produkt']} | Status:{z['status']} | Stop:{z['real_stop']}")
        
    print("\nWORKOWANIA:")
    for w in worki:
        print(f"ID:{w['id']} | Prod:{w['produkt']} | Status:{w['status']}")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
