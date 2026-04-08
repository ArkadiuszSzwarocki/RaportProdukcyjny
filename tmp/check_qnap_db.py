import mysql.connector
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

DB_CONFIG = {
    'host': 'raportprodukcji.mycloudnas.com', # Use the DDNS address
    'port': int(os.getenv('DB_PORT', 3307)),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'user': os.getenv('DB_USER', 'biblioteka'),
    'password': os.getenv('DB_PASSWORD', ''),
    'charset': 'utf8mb4',
    'connection_timeout': 10
}

def test_connection():
    print(f"Próba połączenia z bazą na QNAP (DDNS):")
    print(f"Host: {DB_CONFIG['host']}")
    print(f"Port: {DB_CONFIG['port']}")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"User: {DB_CONFIG['user']}")
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("\n[SUCCESS] Połączenie z bazą danych na QNAP (DDNS) działa!")
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            print(f"Wersja bazy danych: {version[0]}")
            
            # Check some tables
            cursor.execute("SHOW TABLES")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"Liczba tabel: {len(tables)}")
            print(f"Przykładowe tabele: {tables[:5]}")
            
            cursor.close()
            conn.close()
            return True
    except mysql.connector.Error as err:
        print(f"\n[ERROR] Błąd połączenia z bazą na QNAP (DDNS): {err}")
        return False

if __name__ == "__main__":
    test_connection()
