#!/usr/bin/env python
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)

cursor.execute('SELECT id, zasyp_id, produkt, data_planu, status FROM bufor WHERE data_planu = %s ORDER BY id DESC LIMIT 5', ('2026-03-05',))
rows = cursor.fetchall()

if rows:
    print('✓ ZNALEZIONE WPISY W BUFOR NA 2026-03-05:')
    for r in rows:
        print(f'  ID={r["id"]}, zasyp_id={r["zasyp_id"]}, produkt={r["produkt"]}, status={r["status"]}')
else:
    print('✗ BRAK WPISÓW W BUFOR NA 2026-03-05')

conn.close()
