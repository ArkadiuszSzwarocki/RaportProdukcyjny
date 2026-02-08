import mysql.connector
from app.config import DB_CONFIG

conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# Zmień status Testowy1 na 'w toku'
cursor.execute('''
UPDATE plan_produkcji
SET status = 'w toku'
WHERE sekcja = 'Workowanie' 
  AND produkt = 'Testowy1'
  AND DATE(data_planu) = '2026-02-08'
LIMIT 1
''')

print(f'Changed {cursor.rowcount} rows to w toku')

conn.commit()
cursor.close()
conn.close()

# Now check get_active_products again
import sys
sys.path.insert(0, '.')
from app.services.dashboard_service import DashboardService
from datetime import date

active = DashboardService.get_active_products(date(2026, 2, 8))
print(f'get_active_products after Testowy1 status=w toku: {active}')
is_testowy1_present = 'Testowy1' in active
print(f'Testowy1 in active: {is_testowy1_present}')
