import os
import sys

# Upewnij się, że główny katalog aplikacji jest w ścieżce
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.db import get_db_connection

def create_print_jobs_table():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        print("Creating table print_jobs...")
        
        sql = """
        CREATE TABLE IF NOT EXISTS print_jobs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            printer_ip VARCHAR(255) NOT NULL,
            printer_name VARCHAR(255),
            zpl_content TEXT NOT NULL,
            status VARCHAR(50) DEFAULT 'PENDING',
            retry_count INT DEFAULT 0,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        cursor.execute(sql)
        conn.commit()
        print("Table print_jobs created successfully.")
    except Exception as e:
        print(f"Fatal Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    create_print_jobs_table()
