
import mysql.connector
from app.config import DB_CONFIG

def check_db():
    try:
        config = DB_CONFIG.copy()
        config.pop('database', None)
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        for db_name in ['biblioteka', 'biblioteka_testowa']:
            print(f"\n--- DATABASE: {db_name} ---")
            conn.database = db_name
            cursor.execute("SHOW TABLES LIKE 'magazyn_%'")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"Magazyn tables: {tables}")
            
            for t in ['magazyn_surowce', 'magazyn_opakowania']:
                if t in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {t}")
                    count = cursor.fetchone()[0]
                    print(f"  {t}: {count} rows")
                    
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
