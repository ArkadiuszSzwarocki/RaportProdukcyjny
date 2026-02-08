import mysql.connector
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'biblioteka'),
    'port': int(os.getenv('DB_PORT', 3306))
}

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, produkt, status, is_deleted
    FROM plan_produkcji 
    WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
    ORDER BY produkt
    ''', (date.today(),))
    
    print('=== PLAN PRODUKCJI WORKOWANIE ===')
    for row in cursor.fetchall():
        print(f'id={row[0]}, produkt={row[1]}, status={row[2]}, is_deleted={row[3]}')
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
