import mysql.connector
from config import DB_CONFIG

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG, buffered=True)

def setup_database():
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        
        # Tabele
        cursor.execute("CREATE TABLE IF NOT EXISTS pracownicy (id INT AUTO_INCREMENT PRIMARY KEY, imie_nazwisko VARCHAR(255) NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS uzytkownicy (id INT AUTO_INCREMENT PRIMARY KEY, login VARCHAR(50) UNIQUE NOT NULL, haslo VARCHAR(50) NOT NULL, rola VARCHAR(20) NOT NULL)")
        cursor.execute("INSERT IGNORE INTO uzytkownicy (login, haslo, rola) VALUES ('admin', 'masterkey', 'admin'), ('lider', 'admin123', 'lider'), ('planista', 'plan123', 'planista'), ('pracownik', 'user123', 'pracownik')")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS dziennik_zmiany (
            id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE NOT NULL, sekcja VARCHAR(50) NOT NULL, 
            pracownik_id INT, problem TEXT, status VARCHAR(20) DEFAULT 'roboczy', 
            czas_start TIME NULL, czas_stop TIME NULL, kategoria VARCHAR(50) NULL, 
            FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id))""")
        
        cursor.execute("CREATE TABLE IF NOT EXISTS obsada_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE NOT NULL, sekcja VARCHAR(50) NOT NULL, pracownik_id INT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS raporty_koncowe (id INT AUTO_INCREMENT PRIMARY KEY, data_raportu DATE NOT NULL, lider_uwagi TEXT, data_utworzenia TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS plan_produkcji (
            id INT AUTO_INCREMENT PRIMARY KEY, data_planu DATE NOT NULL, sekcja VARCHAR(50) DEFAULT 'Zasyp', 
            produkt VARCHAR(255) NOT NULL, tonaz FLOAT NOT NULL, status VARCHAR(20) DEFAULT 'zaplanowane', 
            real_start DATETIME NULL, real_stop DATETIME NULL, tonaz_rzeczywisty FLOAT NULL)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS palety_workowanie (
            id INT AUTO_INCREMENT PRIMARY KEY, plan_id INT NOT NULL, waga FLOAT NOT NULL, 
            data_dodania TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS obecnosc (
            id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE NOT NULL, pracownik_id INT NOT NULL, 
            typ VARCHAR(50) NOT NULL, ilosc_godzin FLOAT DEFAULT 0, komentarz TEXT, 
            FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id))""")
        
        # Migracje (naprawa brakujących kolumn)
        try: cursor.execute("ALTER TABLE dziennik_zmiany ADD COLUMN kategoria VARCHAR(50) NULL")
        except: pass
        try: cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN tonaz_rzeczywisty FLOAT NULL")
        except: pass
        try: 
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN real_start DATETIME NULL")
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN real_stop DATETIME NULL")
        except: pass
        try: cursor.execute("ALTER TABLE obecnosc MODIFY COLUMN ilosc_godzin FLOAT")
        except: pass

        conn.commit(); conn.close()
    except Exception as e: print(f"Błąd bazy: {e}")