import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "raport_produkcyjny"),
    port=int(os.getenv("DB_PORT", 3306))
)
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, sekcja, produkt, status, data_planu FROM plan_produkcji_agro WHERE status='zakonczone' ORDER BY data_planu DESC LIMIT 10")
for r in cursor.fetchall():
    print(r)
