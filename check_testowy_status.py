#!/usr/bin/env python3
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check Testowy plans  
cursor.execute("""
    SELECT id, produkt, sekcja, status, data_planu FROM plan_produkcji
    WHERE produkt IN ('Testowy2', 'Testowy4')
    ORDER BY sekcja, produkt
""")

print("\n🔍 Testowy plany:")
for row in cursor.fetchall():
    z_id, prod, sekcja, status, data = row
    print(f"  ID={z_id:4d} | {sekcja:12s} | {prod:10s} | {status:12s} | {data}")

# Check bufor
cursor.execute("""
    SELECT COUNT(*) FROM bufor WHERE status='aktywny'
""")
count = cursor.fetchone()[0]
print(f"\n📊 Bufor entries: {count}")

cursor.close()
conn.close()
