import os
import sys
from datetime import date
from flask import Flask

# Add the project root to sys.path
sys.path.append(r'c:\Users\arkad\Documents\GitHub\RaportProdukcyjny')

from app.db import set_active_database_name, get_db_connection
from app.utils.queries import QueryHelper

app = Flask(__name__)

def debug_query():
    with app.app_context():
        set_active_database_name('biblioteka_testowa')
        today = date.today()
        
        print(f"DEBUG: Querying Zasyp for AGRO on {today}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        plans = QueryHelper.get_plan_produkcji(today, 'Zasyp', linia='AGRO', cursor=cursor)
        print(f"Found {len(plans)} plans.")
        for p in plans:
            print(p)
            
        cursor.close()
        conn.close()

if __name__ == "__main__":
    debug_query()
