
import mysql.connector
from app.config import DB_CONFIG

def check_db():
    try:
        # Connect without specifying database to see all
        config = DB_CONFIG.copy()
        db_name = config.pop('database', 'biblioteka')
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        print("--- DATABASES ---")
        cursor.execute("SHOW DATABASES")
        for db in cursor.fetchall():
            print(db[0])
            
        print(f"\n--- TABLES IN {db_name} ---")
        conn.database = db_name
        cursor.execute("SHOW TABLES")
        for table in cursor.fetchall():
            print(table[0])
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
