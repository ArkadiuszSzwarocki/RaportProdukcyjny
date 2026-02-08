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

cursor.execute('''
SELECT id, produkt, sekcja, status, is_deleted
FROM plan_produkcji 
WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie'
ORDER BY produkt
''', (date.today(),))

print('=== WSZYSCY w plan_produkcji Workowanie ===')
for row in cursor.fetchall():
    print(f'  id={row[0]:3} | {row[1]:12} | status={row[3]:12} | is_deleted={row[4]}')
cursor.execute('''
SELECT produkt, MIN(kolejka) as min_queue
FROM bufor 
WHERE DATE(data_planu) = %s AND status = 'aktywny'
GROUP BY produkt
ORDER BY min_queue
''', (date.today(),))

print('=== BUFOR MIN QUEUE (co powinna zwrócić SQL query) ===')
rows = cursor.fetchall()
bufor_min_queue = {}
for row in rows:
    if row and len(row) >= 2:
        prod, min_q = row[0], row[1]
        bufor_min_queue[prod] = min_q
        print(f'  {prod:12} -> min_queue = {min_q}')

# Sprawdź work_first_map
cursor.execute('''
SELECT produkt, id 
FROM plan_produkcji 
WHERE sekcja = 'Workowanie' 
  AND DATE(data_planu) = %s
  AND status = 'zaplanowane'
ORDER BY produkt
''', (date.today(),))

print('\n=== WORK_FIRST_MAP (do jakich ID przypisać) ===')
work_first_map = {}
for row in cursor.fetchall():
    if row and len(row) >= 2:
        prod, w_id = row[0], row[1]
        work_first_map[prod] = w_id
        print(f'  {prod:12} -> work_id = {w_id}')

# Oblicz allowed_work_start_ids
allowed_work_start_ids = set()
print('\n=== OBLICZANIE ALLOWED_WORK_START_IDS ===')
for prod, min_queue in bufor_min_queue.items():
    if min_queue == 1:
        if prod in work_first_map:
            allowed_work_start_ids.add(work_first_map[prod])
            print(f'  START AKTYWNY: {prod} (id={work_first_map[prod]}) - kolejka = 1')
        else:
            print(f'  UWAGA: {prod} ma min_queue=1 ale NIE MA work_first_map!')
    else:
        print(f'  START ZABLOKOWANY: {prod} - min_queue = {min_queue}')

print(f'\nFinal allowed_work_start_ids: {allowed_work_start_ids}')

cursor.close()
conn.close()
