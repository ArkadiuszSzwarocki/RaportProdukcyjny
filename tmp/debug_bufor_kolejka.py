import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

today = '2026-03-30'
print(f"--- Bufor entries for {today} ---")
try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('bufor', 'PSD')
    query = f"SELECT id, produkt, kolejka, status FROM {table} WHERE DATE(data_planu)='{today}'"
    cursor.execute(query)
    results = cursor.fetchall()
    for row in results:
        print(f"ID: {row['id']} | Produkt: {row['produkt']} | Kolejka: {row['kolejka']} | Status: {row['status']}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
