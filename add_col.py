import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from app.db import get_db_connection

def add_column():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE szarze ADD COLUMN nr_szarzy INT NULL")
        print("Column added effectively.")
    except Exception as e:
        print(f"Error (maybe already exists?): {e}")
    finally:
        conn.commit()
        cursor.close()
        conn.close()

if __name__ == '__main__':
    add_column()
