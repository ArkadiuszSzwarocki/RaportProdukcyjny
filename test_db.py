import sys
import os
sys.path.append('A:\\GitHub\\RaportProdukcyjny')
from app.db import get_db_connection
from datetime import date
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute('SELECT id, produkt, status, sekcja, data_planu FROM plan_produkcji_agro ORDER BY id DESC LIMIT 15')
for row in cursor.fetchall():
    print(row)

from app.utils.queries_split.production import ProductionQueries
today = date.today()
print("Plan dla Workowanie:", ProductionQueries.get_plan_produkcji(today, 'Workowanie', 'AGRO'))
conn.close()
