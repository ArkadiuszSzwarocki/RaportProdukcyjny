
import mysql.connector
from app.config import DB_CONFIG
from werkzeug.security import generate_password_hash

def reset_admin():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        new_pass = generate_password_hash('admin123')
        cursor.execute("UPDATE uzytkownicy SET haslo = %s WHERE login = 'admin'", (new_pass,))
        conn.commit()
        print("Admin password reset to 'admin123'")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    reset_admin()
