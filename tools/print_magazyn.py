#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from app.db import get_db_connection
from pprint import pprint

conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT id,paleta_workowanie_id,plan_id,data_planu,produkt,waga_netto,data_potwierdzenia,created_at FROM magazyn_palety ORDER BY id DESC LIMIT 20')
rows = cur.fetchall()
for r in rows:
    pprint(r)

cur.close()
conn.close()
