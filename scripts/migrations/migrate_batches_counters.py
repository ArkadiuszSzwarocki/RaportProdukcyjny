import sys
import os

# Set up the path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from app.db import get_db_connection

def migrate():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Creating magazyn_surowce_liczniki_partii table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_surowce_liczniki_partii (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa_surowca VARCHAR(255) NOT NULL UNIQUE,
            aktualny_numer_partii INT DEFAULT 1,
            palet_w_obecnej_partii INT DEFAULT 0,
            aktualna_data_produkcji DATE DEFAULT NULL,
            aktualna_data_przydatnosci DATE DEFAULT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    conn.commit()
    conn.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
