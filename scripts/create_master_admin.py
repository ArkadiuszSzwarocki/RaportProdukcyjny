from werkzeug.security import generate_password_hash
from app.db import get_db_connection
import sys

def create_master_admin(password):
    conn = get_db_connection()
    cursor = conn.cursor()
    login = 'MasterAdmin'
    hashed = generate_password_hash(password, method='pbkdf2:sha256')
    rola = 'masteradmin'
    grupa = 'ALL'
    
    try:
        # Check if already exists
        cursor.execute("SELECT id FROM uzytkownicy WHERE login = %s", (login,))
        if cursor.fetchone():
            cursor.execute("UPDATE uzytkownicy SET haslo = %s, rola = %s WHERE login = %s", (hashed, rola, login))
            print(f"User {login} updated successfully.")
        else:
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola, grupa) VALUES (%s, %s, %s, %s)", (login, hashed, rola, grupa))
            print(f"User {login} created successfully.")
        conn.commit()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    pw = sys.argv[1] if len(sys.argv) > 1 else 'MasterAdmin123!'
    create_master_admin(pw)
