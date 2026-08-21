import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, produkt, typ_produkcji, sekcja, data_planu FROM plan_produkcji_agro WHERE sekcja = 'Workowanie' ORDER BY id DESC LIMIT 10")
plans = cursor.fetchall()
for p in plans:
    print(f"ID: {p['id']}, Produkt: {p['produkt']}, Typ: {p['typ_produkcji']}, Sekcja: {p['sekcja']}, Data: {p['data_planu']}")
conn.close()
