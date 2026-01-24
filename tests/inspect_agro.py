import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import get_db_connection

DATE = '2026-01-23'
PROD = 'AGRO MILK TOP'

conn = get_db_connection()
cur = conn.cursor()
cur.execute("SELECT sekcja, produkt, tonaz, tonaz_rzeczywisty FROM plan_produkcji WHERE data_planu = %s AND produkt = %s", (DATE, PROD))
rows = cur.fetchall()
print('Rows for', PROD)
for r in rows:
    print(r)

# compute values
zasyp_plan = None
work_wyk = None
for r in rows:
    sekcja, produkt, tonaz, tonaz_rzeczywisty = r
    if sekcja == 'Zasyp':
        zasyp_plan = tonaz
    if sekcja == 'Workowanie':
        work_wyk = tonaz_rzeczywisty

print('Zasyp plan raw:', zasyp_plan)
print('Workowanie wykonanie raw:', work_wyk)
try:
    zasyp_f = float(zasyp_plan) if zasyp_plan is not None else None
    work_f = float(work_wyk) if work_wyk is not None else None
    print('Diff (work - zasyp) =', work_f - zasyp_f)
except Exception as e:
    print('Error computing diff:', e)

conn.close()
