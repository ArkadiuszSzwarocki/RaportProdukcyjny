import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST", "localhost"),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
    database=os.getenv("DB_NAME", "raport_produkcyjny")
)
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, sekcja, produkt, status, zasyp_id FROM plan_produkcji_agro WHERE data_planu = '2026-06-20'")
rows = cursor.fetchall()
for r in rows:
    print(r)
