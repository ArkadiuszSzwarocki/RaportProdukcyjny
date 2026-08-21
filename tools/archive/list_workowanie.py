#!/usr/bin/env python3
from app.db import get_db_connection
from datetime import date
import sys

date_str = sys.argv[1] if len(sys.argv)>1 else date.today().isoformat()
conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT id, produkt, sekcja, status, data_planu, real_start, real_stop FROM plan_produkcji WHERE sekcja='Workowanie' AND DATE(data_planu)=%s ORDER BY id", (date_str,))
rows = cur.fetchall()
print(f'Workowanie plans for {date_str}:')
for r in rows:
    print(r)
conn.close()
