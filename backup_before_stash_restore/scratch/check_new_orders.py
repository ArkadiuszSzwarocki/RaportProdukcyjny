import os
import sys
from datetime import date

# Add the project root to sys.path to import app modules
sys.path.append(r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import get_db_connection, set_active_database_name

def check_new_orders():
    # Switch to test database
    set_active_database_name('biblioteka_testowa')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    today = date.today()
    print(f"Checking orders for date: {today}")
    
    # Check all orders in AGRO for today
    cursor.execute("""
        SELECT id, sekcja, produkt, tonaz, status, data_planu, is_deleted 
        FROM plan_produkcji_agro 
        WHERE DATE(data_planu) = %s
    """, (today,))
    
    orders = cursor.fetchall()
    print("\n--- plan_produkcji_agro ---")
    if not orders:
        print("Brak zleceń na dziś w AGRO.")
        # Check all orders to see what's there
        cursor.execute("SELECT id, sekcja, produkt, status, data_planu FROM plan_produkcji_agro ORDER BY id DESC LIMIT 5")
        recent = cursor.fetchall()
        print("\nOstatnie 5 zleceń (dowolna data):")
        for r in recent:
            print(r)
    else:
        for o in orders:
            print(o)
            
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_new_orders()
