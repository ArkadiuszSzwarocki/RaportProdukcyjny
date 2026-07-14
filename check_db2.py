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
cur.execute("SELECT id, produkt, nr_palety, plan_id FROM palety_agro WHERE nr_palety = 'AGR000001783968780508'")
row = cur.fetchone()
print('palety_agro:', row)
