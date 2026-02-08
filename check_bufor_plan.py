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

print('=== BUFOR (status = aktywny) ===')
cursor.execute('''
SELECT produkt, kolejka, status, plan_produkcji_id
FROM bufor 
WHERE DATE(data_planu) = %s AND status = 'aktywny'
ORDER BY kolejka
''', (date.today(),))

for row in cursor.fetchall():
    print(f'  {row[0]:12} | kolejka={row[1]} | status={row[2]:12} | plan_id={row[3]}')

print('\n=== PLAN_PRODUKCJI (sekcja Workowanie) ===')
cursor.execute('''
SELECT id, produkt, sekcja, status,Data_planu
FROM plan_produkcji 
WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
ORDER BY produkt
''', (date.today(),))

for row in cursor.fetchall():
    print(f'  id={row[0]:3} | {row[1]:12} | {row[2]:15} | status={row[3]:12}')

cursor.close()
conn.close()
