import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

today = '2026-03-30'
print(f"--- All pending Workowanie orders for {today} ---")
try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('plan_produkcji', 'PSD')
    query = f"SELECT id, produkt, status FROM {table} WHERE data_planu='{today}' AND sekcja='Workowanie' AND status='zaplanowane'"
    cursor.execute(query)
    results = cursor.fetchall()
    for row in results:
        print(f"ID: {row['id']} | Produkt: {row['produkt']} | Status: {row['status']}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
