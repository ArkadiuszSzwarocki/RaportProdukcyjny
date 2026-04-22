import sys
import os
import json
import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import get_db_connection

def inspect():
    conn = get_db_connection()
    c = conn.cursor(dictionary=True)
    c.execute("SELECT id, produkt, sekcja, status, tonaz, tonaz_rzeczywisty, data_planu FROM plan_produkcji_agro WHERE data_planu='2026-04-21' ORDER BY id DESC")
    rows = c.fetchall()
    
    def default(o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
            
    with open('tmp/out.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, default=default)
        
    conn.close()

if __name__ == '__main__':
    inspect()
