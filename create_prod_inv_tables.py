from app.db import get_db_connection

def create_tables():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_inwentaryzacja_produkcji_sesje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(10) NOT NULL,
            status ENUM('OPEN', 'CLOSED', 'APPLIED') DEFAULT 'OPEN',
            created_by VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME,
            comment TEXT,
            lokalizacja VARCHAR(100) DEFAULT 'Wszystko'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_inwentaryzacja_produkcji_wpisy (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sesja_id INT NOT NULL,
            ruch_id INT,
            zbiornik VARCHAR(50),
            surowiec_nazwa VARCHAR(255),
            waga_systemowa FLOAT DEFAULT 0,
            waga_faktyczna FLOAT DEFAULT 0,
            data_wpisu DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_login VARCHAR(100),
            FOREIGN KEY (sesja_id) REFERENCES magazyn_inwentaryzacja_produkcji_sesje(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    print("Tables created")

if __name__ == "__main__":
    create_tables()
