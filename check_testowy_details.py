#!/usr/bin/env python3
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdzenie Testowy2 i Testowy4 - która data, jaki real_start
cursor.execute("""
    SELECT z.id, z.produkt, z.data_planu, z.status, z.real_start, z.sekcja
    FROM plan_produkcji z
    WHERE z.produkt IN ('Testowy2', 'Testowy4')
    ORDER BY z.data_planu DESC, z.real_start DESC
""")

rows = cursor.fetchall()
print("\n🔎 Testowy2 i Testowy4 - wszystkie rekordy:")
for row in rows:
    z_id, produkt, data, status, real_start, sekcja = row
    start_time = real_start.strftime('%Y-%m-%d %H:%M:%S') if real_start else 'NULL'
    print(f"  ID={z_id:4d} | {produkt:12s} | {sekcja:12s} | Data={data} | Status={status:12s} | real_start={start_time}")

# Sprawdzenie jakie produkty są w buforze i z jakich dat
print("\n📋 Produkty w buforze i ich daty.")
cursor.execute("""
    SELECT b.id, b.produkt, b.data_planu, z.real_start, b.status
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
    WHERE b.status = 'aktywny'
    ORDER BY b.data_planu DESC, b.kolejka ASC
""")

rows = cursor.fetchall()
for row in rows:
    buf_id, produkt, data, real_start, status = row
    start_time = real_start.strftime('%H:%M:%S') if real_start else 'NULL'
    print(f"  {data} | {produkt:20s} | real_start={start_time} | status={status}")

cursor.close()
conn.close()
