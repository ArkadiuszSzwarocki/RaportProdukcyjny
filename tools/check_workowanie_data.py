#!/usr/bin/env python
# -*- coding: utf-8 -*-
from db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()

# Check Workowanie plans
cursor.execute("SELECT id, produkt FROM plan_produkcji WHERE sekcja='Workowanie' LIMIT 5")
plans = cursor.fetchall()
print(f'Workowanie plans: {plans}')

# Check paletki for each Workowanie plan
if plans:
    for plan_id, produkt in plans:
        cursor.execute("SELECT id, waga, data_dodania FROM palety_workowanie WHERE plan_id=%s LIMIT 5", (plan_id,))
        paletki = cursor.fetchall()
        print(f'  Plan {plan_id} ({produkt}): {len(paletki)} paletki')
        for pal in paletki:
            print(f'    - ID={pal[0]}, waga={pal[1]}, data={pal[2]}')

cursor.close()
conn.close()
