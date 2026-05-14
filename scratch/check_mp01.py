import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def check_db():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            port=int(os.getenv('DB_PORT', 3306))
        )
        cur = conn.cursor(dictionary=True)
        
        print("--- Pallets at MP01 (Floor) ---")
        cur.execute("SELECT id, nazwa, lokalizacja FROM magazyn_surowce WHERE lokalizacja = 'MP01' AND stan_magazynowy > 0")
        print("Surowce:", cur.fetchall())
        
        cur.execute("SELECT id, nazwa, lokalizacja FROM magazyn_opakowania WHERE lokalizacja = 'MP01' AND stan_magazynowy > 0")
        print("Opakowania:", cur.fetchall())

        print("\n--- Pallets at Racks R01-R03 (MP01 Hall) ---")
        cur.execute("SELECT id, nazwa, lokalizacja FROM magazyn_surowce WHERE (lokalizacja LIKE 'R01%' OR lokalizacja LIKE 'R02%' OR lokalizacja LIKE 'R03%') AND stan_magazynowy > 0 LIMIT 5")
        print("Surowce (Sample):", cur.fetchall())

        conn.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_db()
