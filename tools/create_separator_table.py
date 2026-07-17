import sys
import os

# Dodanie głównego katalogu do ścieżki
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db import get_db_connection

def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS czyszczenie_separatorow (
                id INT AUTO_INCREMENT PRIMARY KEY,
                linia VARCHAR(50) NOT NULL,
                data_planu DATE NOT NULL,
                data_wykonania DATETIME NULL,
                login_wykonawcy VARCHAR(50) NULL,
                status VARCHAR(20) DEFAULT 'pending',
                komentarz TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("Tabela czyszczenie_separatorow została pomyślnie utworzona.")
    except Exception as e:
        print(f"Błąd podczas tworzenia tabeli: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    create_table()
