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
cur.execute("SELECT id, sekcja, produkt, status, typ_zlecenia FROM plan_produkcji_agro WHERE sekcja='Workowanie' AND status='zaplanowane'")
print(cur.fetchall())
