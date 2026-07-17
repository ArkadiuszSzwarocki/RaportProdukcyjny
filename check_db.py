import os
import sys
import mysql.connector
from dotenv import load_dotenv

sys.path.insert(0, 'a:/GitHub/RaportProdukcyjny')
load_dotenv('a:/GitHub/RaportProdukcyjny/.env')

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cur = conn.cursor(dictionary=True)
cur.execute("SELECT id, produkt, nr_palety, plan_id FROM magazyn_palety_agro WHERE nr_palety = 'AGR000001783968780508'")
row = cur.fetchone()
print('magazyn_palety_agro:', row)

if not row:
    cur.execute("SELECT id, nr_palety, plan_id FROM palety_agro WHERE nr_palety = 'AGR000001783968780508'")
    row2 = cur.fetchone()
    print('palety_agro:', row2)
    if row2 and row2['plan_id']:
        cur.execute("SELECT id, produkt FROM plan_produkcji_agro WHERE id = %s", (row2['plan_id'],))
        print('plan_produkcji_agro:', cur.fetchone())
else:
    if row['plan_id']:
        cur.execute("SELECT id, produkt FROM plan_produkcji_agro WHERE id = %s", (row['plan_id'],))
        print('plan_produkcji_agro:', cur.fetchone())
        cur.execute("SELECT id, produkt FROM plan_produkcji WHERE id = %s", (row['plan_id'],))
        print('plan_produkcji:', cur.fetchone())
