
import mysql.connector
from app.config import DB_CONFIG
from datetime import date

def check_full_orders():
    try:
        config = DB_CONFIG.copy()
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        today = date.today()
        
        print("\n--- PSD ZASYP ORDERS ---")
        cursor.execute("SELECT * FROM plan_produkcji WHERE data_planu = %s AND sekcja = 'Zasyp'", (today,))
        for r in cursor.fetchall():
            print(r)
            
        print("\n--- AGRO WORKOWANIE ORDERS ---")
        cursor.execute("SELECT * FROM plan_produkcji_agro WHERE data_planu = %s AND sekcja = 'Workowanie'", (today,))
        for r in cursor.fetchall():
            print(r)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_full_orders()
