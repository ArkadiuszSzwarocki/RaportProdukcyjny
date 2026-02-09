#!/usr/bin/env python3
from app.db import get_db_connection, refresh_bufor_queue

# Refresh bufor aby renumerować
refresh_bufor_queue()

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT b.kolejka, b.produkt, b.data_planu 
    FROM bufor b
    WHERE b.status = 'aktywny'
    ORDER BY b.kolejka ASC
""")

rows = cursor.fetchall()
print("\n✅ BUFOR KOLEJKA (po refresh):")
for row in rows:
    kolejka, produkt, data = row
    print(f"  {kolejka:2d}. {produkt:20s} | {data}")

cursor.close()
conn.close()
