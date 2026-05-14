import mysql.connector
from app.config import DB_CONFIG
from datetime import date
from app.utils.queries import QueryHelper
from app.db import set_active_database_name

def check_queries():
    # Switch to test database
    set_active_database_name('biblioteka_testowa')
    
    today = date.today()
    print(f"Checking QueryHelper.get_plan_produkcji for {today}")
    
    print("\n--- AGRO Workowanie ---")
    plans = QueryHelper.get_plan_produkcji(today, 'Workowanie', linia='AGRO')
    for p in plans:
        print(p)
        
    print("\n--- AGRO Zasyp ---")
    plans = QueryHelper.get_plan_produkcji(today, 'Zasyp', linia='AGRO')
    for p in plans:
        print(p)

if __name__ == "__main__":
    check_queries()
