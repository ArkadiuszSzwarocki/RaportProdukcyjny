#!/usr/bin/env python
import mysql.connector

conn = mysql.connector.connect(
    host='192.168.0.18',
    port=3307,
    user='biblioteka',
    password='Filipinka2025',
    database='biblioteka'
)

cursor = conn.cursor()

# Szukaj plany do usunięcia
print("=== PLANY ZAPLANOWANE (Zasyp) ===")
cursor.execute("""SELECT id, data_planu, produkt, status, is_deleted, sekcja FROM plan_produkcji WHERE sekcja='Zasyp' AND status='zaplanowane' ORDER BY id DESC LIMIT 15""")
for row in cursor.fetchall():
    print(f'ID: {row[0]}, Data: {row[1]}, Produkt: {row[2]}, Status: {row[3]}, is_deleted: {row[4]}, Sekcja: {row[5]}')

print("\n=== PLANY USUNIĘTE (Zasyp) ===")
cursor.execute("""SELECT id, data_planu, produkt, status, is_deleted, sekcja FROM plan_produkcji WHERE sekcja='Zasyp' AND is_deleted=1 ORDER BY id DESC LIMIT 10""")
for row in cursor.fetchall():
    print(f'ID: {row[0]}, Data: {row[1]}, Produkt: {row[2]}, Status: {row[3]}, is_deleted: {row[4]}, Sekcja: {row[5]}')

print("\n=== PLAN O TEKŚCIE 'Zlecenie' ===")
cursor.execute("""SELECT id, data_planu, produkt, status, is_deleted, sekcja FROM plan_produkcji WHERE produkt LIKE '%lecenie%' LIMIT 10""")
for row in cursor.fetchall():
    print(f'ID: {row[0]}, Data: {row[1]}, Produkt: {row[2]}, Status: {row[3]}, is_deleted: {row[4]}, Sekcja: {row[5]}')

conn.close()
