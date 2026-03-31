import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

today = '2026-03-30'
print(f"--- Checking line: PSD for {today} ---")
try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    table = get_table_name('plan_produkcji', 'PSD')
    query = f"SELECT id, produkt, status, sekcja, tonaz, tonaz_rzeczywisty FROM {table} WHERE data_planu='{today}' AND produkt LIKE '%GÓR-PASZ INSTANT%'"
    cursor.execute(query)
    results = cursor.fetchall()
    for row in results:
        print(f"ID: {row['id']} | Produkt: {row['produkt']} | Status: {row['status']} | Sekcja: {row['sekcja']} | Tonaż: {row['tonaz']} | Realizacja: {row['tonaz_rzeczywisty']}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
