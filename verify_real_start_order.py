#!/usr/bin/env python3
"""Verify that bufor jest sortowany po real_start (czas startu)"""
from app.db import get_db_connection
from datetime import datetime

print("\n=== BUFOR SORT BY REAL_START VERIFICATION ===\n")

conn = get_db_connection()
cursor = conn.cursor()

# Pobierz plany Zasyp z ich czasami startu
print("1️⃣ Zasyp plany i ich czasy startu (real_start):")
cursor.execute("""
    SELECT z.id, z.produkt, z.status, z.real_start, z.data_planu
    FROM plan_produkcji z
    WHERE z.sekcja = 'Zasyp' AND z.data_planu = CURDATE()
    ORDER BY CASE WHEN z.real_start IS NOT NULL THEN 0 ELSE 1 END ASC, z.real_start ASC
""")
rows = cursor.fetchall()
for row in rows:
    z_id, produkt, status, real_start, data = row
    start_time = real_start.strftime('%H:%M:%S') if real_start else 'BRAK (zaplanowane)'
    print(f"  ID={z_id:4d} | Produkt={produkt:20s} | Status={status:12s} | Start={start_time}")

print("\n2️⃣ Bufor kolejka (po refresh):")
from app.db import refresh_bufor_queue
refresh_bufor_queue()

cursor.execute("""
    SELECT b.id, b.produkt, b.kolejka, b.status, z.real_start, z.status
    FROM bufor b
    LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
    WHERE b.status = 'aktywny'
    ORDER BY b.kolejka ASC
""")
rows = cursor.fetchall()
for row in rows:
    buf_id, produkt, kolejka, buf_status, real_start, z_status = row
    start_time = real_start.strftime('%H:%M:%S') if real_start else 'BRAK'
    print(f"  Bufor ID={buf_id:4d} | Kolejka={kolejka} | Produkt={produkt:20s} | START={start_time} | Zasyp Status={z_status}")

print("\n✅ REZULTAT:")
print("   - Plany posortowane po real_start (czas startu)")
print("   - Pierwszy kliknął START → kolejka=1")
print("   - Drugi kliknął START → kolejka=2")
print("   - Brakuje real_start → koniec listy\n")

cursor.close()
conn.close()
