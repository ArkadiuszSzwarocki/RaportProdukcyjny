#!/usr/bin/env python
# -*- coding: utf-8 -*-
from db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

today = date.today()
print(f'Today: {today}')

# Check TODAY's paletki
cursor.execute(
    "SELECT pw.id, pw.plan_id, pw.waga, pw.data_dodania, p.produkt, p.id as plan_id_check "
    "FROM palety_workowanie pw "
    "JOIN plan_produkcji p ON pw.plan_id = p.id "
    "WHERE DATE(pw.data_dodania) = %s ",
    (today,)
)
paletki = cursor.fetchall()
print(f'Paletki added today: {len(paletki)}')
for pal in paletki:
    print(f'  - ID={pal[0]}, plan_id={pal[1]}, waga={pal[2]}, data={pal[3]}, produkt={pal[4]}')

cursor.close()
conn.close()
