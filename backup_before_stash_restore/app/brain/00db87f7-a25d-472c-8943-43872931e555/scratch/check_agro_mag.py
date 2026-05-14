
import mysql.connector
from app.config import DB_CONFIG

def check_more():
    try:
        config = DB_CONFIG.copy()
        config.pop('database', None)
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        for t in ['magazyn_agro_slownik_surowce', 'magazyn_agro_ruch']:
            print(f"\n--- TABLE: {t} ---")
            
            conn.database = 'biblioteka'
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            c1 = cursor.fetchone()[0]
            
            conn.database = 'biblioteka_testowa'
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            c2 = cursor.fetchone()[0]
            
            print(f"  biblioteka: {c1} rows")
            print(f"  biblioteka_testowa: {c2} rows")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_more()
