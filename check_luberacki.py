import os
import sys
# Set up paths to import from 'app'
sys.path.append(os.getcwd())

from app.db import get_db_connection

def check_user():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT login, rola, grupa FROM uzytkownicy WHERE login LIKE '%Luber%'")
        users = cursor.fetchall()
        print(f"SEARCH_USERS: {users}")
        
        cursor.execute("SELECT id, imie_nazwisko, grupa FROM pracownicy WHERE imie_nazwisko LIKE '%Luber%'")
        prac = cursor.fetchall()
        print(f"SEARCH_PRAC: {prac}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    check_user()
