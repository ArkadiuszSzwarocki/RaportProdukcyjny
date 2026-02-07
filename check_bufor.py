#!/usr/bin/env python3
import sys
sys.path.insert(0, '/c/Users/arkad/Documents/GitHub/RaportProdukcyjny')

from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Count Zasyp orders for 2026-02-07
cursor.execute("SELECT COUNT(*) FROM plan_produkcji WHERE sekcja = %s AND data_planu = %s", 
               ('Zasyp', '2026-02-07'))
result = cursor.fetchone()
print(f'Total Zasyp orders for 2026-02-07: {result[0]}')

# Get sample orders
cursor.execute("SELECT id, produkt, tonaz_rzeczywisty, nazwa_zlecenia, typ_produkcji, status FROM plan_produkcji WHERE sekcja = %s AND data_planu = %s LIMIT 10", 
               ('Zasyp', '2026-02-07'))
rows = cursor.fetchall()
print(f'\nFound {len(rows)} Zasyp orders:')
for row in rows:
    print(f'  ID: {row[0]}, Produkt: {row[1]}, Tonaz: {row[2]}, Nazwa: {row[3]}, Typ: {row[4]}, Status: {row[5]}')

conn.close()
