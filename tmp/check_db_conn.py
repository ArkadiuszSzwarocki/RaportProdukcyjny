import mysql.connector
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 3307)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),
    'charset': 'utf8mb4',
    'connection_timeout': 5
}

def test_connection():
    print(f"Próba połączenia z bazą danych:")
    print(f"Host: {DB_CONFIG['host']}")
    print(f"Port: {DB_CONFIG['port']}")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"User: {DB_CONFIG['user']}")
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("\n[SUCCESS] Połączenie z bazą danych zakończone sukcesem!")
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"Wersja bazy danych: {version[0]}")
            
            # Check some tables
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print(f"Liczba tabel w bazie: {len(tables)}")
            
            cursor.close()
            conn.close()
            return True
    except mysql.connector.Error as err:
        print(f"\n[ERROR] Błąd połączenia: {err}")
        return False

if __name__ == "__main__":
    test_connection()
