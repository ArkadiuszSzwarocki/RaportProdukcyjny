import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()
c = mysql.connector.connect(
    host=os.getenv('DB_HOST', 'filipinka.myqnapcloud.com'),
    port=int(os.getenv('DB_PORT', 3307)),
    user=os.getenv('DB_USER', 'biblioteka'),
    password=os.getenv('DB_PASSWORD', 'Filipinka2025'),
    database=os.getenv('DB_NAME', 'biblioteka_testowa')
)
cur=c.cursor(dictionary=True)
cur.execute("SELECT MIN(id) as id, nazwa, SUM(stan_magazynowy) as stan_magazynowy FROM magazyn_opakowania WHERE stan_magazynowy > 0 GROUP BY nazwa ORDER BY nazwa")
print(cur.fetchall())
