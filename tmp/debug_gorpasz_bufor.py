import sys
import os
sys.path.append(os.getcwd())
from app.db import get_db_connection, get_table_name

for linia in ['PSD', 'Agro']:
    print(f"--- Bufor check line: {linia} ---")
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        table = get_table_name('bufor', linia)
        query = f"SELECT * FROM {table} WHERE produkt LIKE '%GÓR-PASZ INSTANT%' AND status='aktywny' ORDER BY data_planu DESC LIMIT 5"
        cursor.execute(query)
        results = cursor.fetchall()
        for row in results:
            print(f"ID: {row['id']} | Produkt: {row['produkt']} | Status: {row['status']} | Tonaż: {row['tonaz_rzeczywisty']} | Spakowano: {row['spakowano']} | Data: {row['data_planu']}")
        conn.close()
    except Exception as e:
        print(f"Error on {linia}: {e}")
