import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

today = '2026-03-30'
prods = ['MILK LUX MILK SPECJAL', 'OVER - 4FOAL MILK', 'GÓR-PASZ SUPREME', 'GÓR-PASZ MLEKO LEN']
print(f"--- Checking Workowanie status for earlier products ---")
try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('plan_produkcji', 'PSD')
    for p in prods:
        query = f"SELECT id, produkt, status, sekcja FROM {table} WHERE data_planu='{today}' AND produkt='{p}' AND sekcja='Workowanie'"
        cursor.execute(query)
        results = cursor.fetchall()
        if not results:
            print(f"[{p}] NO Workowanie entry found!")
        for row in results:
            print(f"ID: {row['id']} | Produkt: {row['produkt']} | Status: {row['status']}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
