import os
import sys
sys.path.append(os.getcwd())
from app.db import get_db_connection

def list_tables():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES LIKE '%plan%'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"PLAN_TABLES: {tables}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    list_tables()
