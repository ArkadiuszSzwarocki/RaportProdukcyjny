import sys
import os
from datetime import date
# Ensure project root is on sys.path when running from tools/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db

def main():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    data = str(date.today())
    produkt = 'TEST Produkt'
    tonaz = 100
    sekcja = 'Zasyp'
    typ = 'worki_zgrzewane_25'
    cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (data,))
    res = cursor.fetchone()
    nk = (res[0] if res and res[0] else 0) + 1
    cursor.execute("INSERT INTO plan_produkcji (data_planu, produkt, tonaz, status, sekcja, kolejnosc, typ_produkcji) VALUES (%s, %s, %s, %s, %s, %s, %s)", (data, produkt, tonaz, 'zaplanowane', sekcja, nk, typ))
    conn.commit()
    plan_id = cursor.lastrowid
    conn.close()
    print('Created plan_id', plan_id)

if __name__ == '__main__':
    main()
