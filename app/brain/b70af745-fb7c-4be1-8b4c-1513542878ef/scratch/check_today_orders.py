import mysql.connector
from app.config import DB_CONFIG
from datetime import date

def check_db():
    config = dict(DB_CONFIG)
    config['database'] = 'biblioteka_testowa'
    
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        today = date.today()
        print(f"Checking data for {today} in {config['database']}")
        
        print("\n--- plan_produkcji_agro (AGRO) ---")
        cursor.execute("SELECT id, produkt, sekcja, status, data_planu, is_deleted, zasyp_id FROM plan_produkcji_agro WHERE data_planu = %s", (today,))
        for row in cursor.fetchall():
            print(row)
            
        print("\n--- bufor_agro (AGRO) ---")
        cursor.execute("SELECT id, zasyp_id, produkt, status, tonaz_rzeczywisty, spakowano FROM bufor_agro WHERE data_planu = %s", (today,))
        for row in cursor.fetchall():
            print(row)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
