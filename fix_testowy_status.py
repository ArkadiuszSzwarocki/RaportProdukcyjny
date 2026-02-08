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

print('=== PRZED zmianą ===')
cursor.execute('''
SELECT id, produkt, sekcja, status
FROM plan_produkcji 
WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
ORDER BY produkt
''', (date.today(),))

for row in cursor.fetchall():
    print(f'  id={row[0]:3} | {row[1]:12} | {row[2]:15} | status={row[3]:12}')

print('\n=== Zmieniam Testowy1 i Testowy2 na "zaplanowane" ===')
cursor.execute('''
UPDATE plan_produkcji 
SET status = 'zaplanowane'
WHERE DATE(data_planu) = %s 
  AND sekcja = 'Workowanie'
  AND produkt IN ('Testowy1', 'Testowy2')
  AND status = 'zakończone'
''', (date.today(),))

print(f'Updated rows: {cursor.rowcount}')
conn.commit()

print('\n=== PO zmianie ===')
cursor.execute('''
SELECT id, produkt, sekcja, status
FROM plan_produkcji 
WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
ORDER BY produkt
''', (date.today(),))

for row in cursor.fetchall():
    print(f'  id={row[0]:3} | {row[1]:12} | {row[2]:15} | status={row[3]:12}')

cursor.close()
conn.close()
