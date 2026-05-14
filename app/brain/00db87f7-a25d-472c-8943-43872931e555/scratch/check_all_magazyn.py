
import mysql.connector
from app.config import DB_CONFIG

def check_all_magazyn():
    try:
        config = DB_CONFIG.copy()
        config.pop('database', None)
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        conn.database = 'biblioteka'
        cursor.execute("SHOW TABLES LIKE 'magazyn_%'")
        tables = [t[0] for t in cursor.fetchall()]
        
        for t in tables:
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
    check_all_magazyn()
