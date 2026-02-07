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

print("=== NAPRAWA: UPDATE sekcja ===")

# Pokaż co będzie zmienione
cursor.execute("SELECT COUNT(*) FROM plan_produkcji WHERE LOWER(sekcja)='zasyp' AND sekcja != 'Zasyp'")
count = cursor.fetchone()[0]
print(f"Znaleziono {count} rekordów do naprawy")

if count > 0:
    # UPDATE na "Zasyp"
    cursor.execute("UPDATE plan_produkcji SET sekcja='Zasyp' WHERE LOWER(sekcja)='zasyp'")
    conn.commit()
    print(f"✅ Zaktualizowano {cursor.rowcount} rekordów")
    
    # Sprawdzenie
    cursor.execute("SELECT COUNT(*), sekcja FROM plan_produkcji WHERE LOWER(sekcja)='zasyp' GROUP BY sekcja")
    for row in cursor.fetchall():
        print(f"   {row[1]}: {row[0]} rekordy")

conn.close()
print("\n✅ DONE!")
