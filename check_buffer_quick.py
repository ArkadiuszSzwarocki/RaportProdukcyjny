#!/usr/bin/env python
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, zasyp_id, data_planu, produkt, tonaz_rzeczywisty FROM bufor WHERE DATE(data_planu)='2026-03-05' ORDER BY id DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)
cursor.close()
conn.close()
