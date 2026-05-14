
import mysql.connector
from app.config import DB_CONFIG
from datetime import date

def check_orders():
    try:
        config = DB_CONFIG.copy()
        # config['database'] is biblioteka_testowa
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        today = date.today()
        print(f"Checking orders for today: {today}")
        
        # PSD
        cursor.execute("SELECT id, produkt, sekcja, status FROM plan_produkcji WHERE data_planu = %s", (today,))
        psd = cursor.fetchall()
        print(f"\nPSD orders today ({len(psd)}):")
        for r in psd:
            print(r)
            
        # AGRO
        cursor.execute("SELECT id, produkt, sekcja, status FROM plan_produkcji_agro WHERE data_planu = %s", (today,))
        agro = cursor.fetchall()
        print(f"\nAGRO orders today ({len(agro)}):")
        for r in agro:
            print(r)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_orders()
