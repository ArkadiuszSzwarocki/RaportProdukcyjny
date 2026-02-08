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

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

print('=== SPRAWDZENIE plan_produkcji na dzisiaj ===')
cursor.execute('''
SELECT id, produkt, sekcja, status, data_planu
FROM plan_produkcji 
WHERE DATE(data_planu) = %s
ORDER BY produkt
''', (date.today(),))

for row in cursor.fetchall():
    print(f'  id={row[0]:3} | {row[1]:12} | {row[2]:15} | {row[3]:12} | {row[4]}')

cursor.close()
conn.close()
