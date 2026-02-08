import mysql.connector
from app.config import DB_CONFIG
from datetime import date

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# Pokaż zawartość bufora dla dzisiaj
cursor.execute('''
SELECT produkt, kolejka, spakowano, tonaz_rzeczywisty, status
FROM bufor 
WHERE DATE(data_planu) = %s
ORDER BY kolejka
''', (date.today(),))

print('=== AKTUALNE STANY W BUFORZE ===')
rows = cursor.fetchall()
for row in rows:
    produkt, kolejka, spakowano, tonaz, status = row
    print(f'  Kolejka {kolejka:2}: {produkt:12} | Spakowano: {spakowano:6.0f}kg / {tonaz:6.0f}kg')

# Pokaż które Workowanie powinno mieć START aktywny
print('\n=== KTÓRA KOLEJKA POWINNA MIEĆ AKTYWNY START? ===')
cursor.execute('''
SELECT produkt, MIN(kolejka) as first_queue
FROM bufor 
WHERE DATE(data_planu) = %s AND status = 'aktywny'
GROUP BY produkt
ORDER BY MIN(kolejka)
''', (date.today(),))

rows = cursor.fetchall()
for row in rows:
    produkt, first_queue = row
    print(f'  {produkt:12} -> Kolejka {first_queue} powinna mieć START')

# Pokaż aktualny status Workowania
print('\n=== WORKOWANIE - AKTUALNY STATUS ===')
cursor.execute('''
SELECT id, produkt, status, tonaz
FROM plan_produkcji 
WHERE sekcja = 'Workowanie' AND DATE(data_planu) = %s
ORDER BY produkt
''', (date.today(),))

rows = cursor.fetchall()
for row in rows:
    w_id, produkt, status, tonaz = row
    print(f'  {produkt:12} (id={w_id:3}) Status={status:12} Tonaz={tonaz:6.0f}kg')

cursor.close()
conn.close()
