import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

today = '2026-03-30'
print(f"--- Zasyp finished orders for {today} ---")
try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('plan_produkcji', 'PSD')
    query = f"SELECT id, produkt, real_stop FROM {table} WHERE data_planu='{today}' AND sekcja='Zasyp' AND status='zakonczone' ORDER BY real_stop ASC"
    cursor.execute(query)
    results = cursor.fetchall()
    for row in results:
        print(f"ID: {row['id']} | Produkt: {row['produkt']} | Koniec: {row['real_stop']}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
