import mysql.connector
from app.config import DB_CONFIG
from datetime import date

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# Pokaż zawartość bufora dla dzisiaj - z nową numeracją kolejki
cursor.execute('''
SELECT id, produkt, kolejka, spakowano, tonaz_rzeczywisty, status
FROM bufor 
WHERE DATE(data_planu) = %s
ORDER BY kolejka, id
''', (date.today(),))

print('=== BUFOR - NOWA NUMERACJA KOLEJKI ===\n')
rows = cursor.fetchall()
for row in rows:
    id_buf, produkt, kolejka, spakowano, tonaz, status = row
    print(f'  Kolejka {kolejka:2}: {produkt:12} | Spakowano: {spakowano:7.0f}kg | Tonaz: {tonaz:7.0f}kg')

print(f'\nRazem: {len(rows)} zleceń w buforze')

cursor.close()
conn.close()
