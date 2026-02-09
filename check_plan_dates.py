#!/usr/bin/env python3
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT z.produkt, z.data_planu, z.real_start, z.status
    FROM plan_produkcji z
    WHERE z.sekcja = 'Zasyp'
    ORDER BY z.data_planu DESC, z.real_start DESC
    LIMIT 20
""")

rows = cursor.fetchall()
today = date.today()
print(f"\n📅 Daty planów (ostatnie 20) - dzisiaj to {today}:")
for row in rows:
    prod, data, real_start, status = row
    start_time = real_start.strftime('%H:%M:%S') if real_start else 'NONE'
    is_today = "🔴 DZISIAJ" if data == today else "⚫ STARY"
    print(f"  {data} {is_today:12s} | {prod:20s} | {start_time} | {status}")

cursor.close()
conn.close()
