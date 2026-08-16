from app.db import get_db_connection, get_table_name
from datetime import date

def check_pallets():
    table_pal = get_table_name('palety_workowanie', 'AGRO')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM {table_pal} ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print(f"Ostatnie 5 palet w {table_pal}:")
    for r in rows:
        print(f"ID: {r['id']}, Plan: {r['plan_id']}, Waga: {r['waga']}, Autor: {r['dodal_login']}, Data: {r['data_dodania']}")
    conn.close()

if __name__ == "__main__":
    check_pallets()
