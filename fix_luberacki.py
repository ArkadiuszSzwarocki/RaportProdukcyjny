import os
import sys
sys.path.append(os.getcwd())

from app.db import get_db_connection

def fix_luberacki():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update user
        cursor.execute("UPDATE uzytkownicy SET grupa = 'ALL' WHERE login = 'LuberBar'")
        print(f"Updated uzytkownicy: {cursor.rowcount} rows")
        
        # Update pracownik as well (for consistency)
        cursor.execute("UPDATE pracownicy SET grupa = 'ALL' WHERE imie_nazwisko LIKE '%Luberacki%'")
        print(f"Updated pracownicy: {cursor.rowcount} rows")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("FIX DONE")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    fix_luberacki()
