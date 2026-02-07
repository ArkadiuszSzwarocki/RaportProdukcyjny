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

# Szukaj triggers
print("=== Szukam TRIGGERS na plan_produkcji ===")
cursor.execute("SELECT TRIGGER_NAME, EVENT_MANIPULATION FROM INFORMATION_SCHEMA.TRIGGERS WHERE TRIGGER_SCHEMA='biblioteka' AND EVENT_OBJECT_TABLE='plan_produkcji'")
triggers = cursor.fetchall()

if triggers:
    print('Znaleziono triggery:')
    for t in triggers:
        print(f'  {t[0]}: {t[1]} {t[2]}')
else:
    print('Brak triggerów na tabeli plan_produkcji')

# Sprawdź definicję tabeli
print("\n=== Kolumna sekcja ===")
cursor.execute("SELECT COLUMN_NAME, COLUMN_TYPE, COLLATION_NAME, CHARACTER_SET_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='biblioteka' AND TABLE_NAME='plan_produkcji' AND COLUMN_NAME='sekcja'")
col = cursor.fetchone()
print(f'Nazwa: {col[0]}')
print(f'Typ: {col[1]}')
print(f'Kolacja: {col[2]}')
print(f'Charset: {col[3]}')

# Sprawdź gdzie jest "Zasyp" vs "zasyp"
print("\n=== Baza: Zasyp vs zasyp ===")
cursor.execute("SELECT COUNT(*) as cnt, sekcja FROM plan_produkcji WHERE LOWER(sekcja)='zasyp' GROUP BY sekcja")
for row in cursor.fetchall():
    print(f'  {row[1]}: {row[0]} rekordy')

conn.close()
