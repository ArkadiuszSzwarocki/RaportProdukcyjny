import mysql.connector
import logging
from config import DB_CONFIG
from werkzeug.security import generate_password_hash

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG, buffered=True)

def setup_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. TWORZENIE TABEL (Jeśli nie istnieją)
        cursor.execute("CREATE TABLE IF NOT EXISTS uzytkownicy (id INT AUTO_INCREMENT PRIMARY KEY, login VARCHAR(50) UNIQUE, haslo VARCHAR(255), rola VARCHAR(20))")
        # Ensure 'haslo' column is large enough for modern password hashes
        try:
            cursor.execute("ALTER TABLE uzytkownicy MODIFY haslo VARCHAR(255)")
        except Exception:
            pass
        cursor.execute("CREATE TABLE IF NOT EXISTS pracownicy (id INT AUTO_INCREMENT PRIMARY KEY, imie_nazwisko VARCHAR(100))")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plan_produkcji (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_planu DATE NOT NULL,
                sekcja VARCHAR(50) NOT NULL,
                produkt VARCHAR(100) NOT NULL,
                tonaz FLOAT,
                status VARCHAR(20) DEFAULT 'zaplanowane',
                real_start DATETIME,
                real_stop DATETIME,
                tonaz_rzeczywisty FLOAT,
                kolejnosc INT DEFAULT 0,
                typ_produkcji VARCHAR(20) DEFAULT 'standard',
                wyjasnienie_rozbieznosci TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS palety_workowanie (
                id INT AUTO_INCREMENT PRIMARY KEY,
                plan_id INT,
                waga FLOAT,
                tara FLOAT DEFAULT 0,
                waga_brutto FLOAT DEFAULT 0,
                data_dodania DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("CREATE TABLE IF NOT EXISTS dziennik_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), problem TEXT, czas_start DATETIME, czas_stop DATETIME, status VARCHAR(20) DEFAULT 'roboczy', kategoria VARCHAR(50), pracownik_id INT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS obsada_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), pracownik_id INT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS obecnosc (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, pracownik_id INT, typ VARCHAR(50), ilosc_godzin FLOAT DEFAULT 0, komentarz TEXT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS raporty_koncowe (id INT AUTO_INCREMENT PRIMARY KEY, data_raportu DATE, lider_uwagi TEXT)")

        # 2. AKTUALIZACJA STRUKTURY (MIGRACJE) - Sprawdzamy czy kolumny istnieją
        
        # Sprawdź i dodaj 'wyjasnienie_rozbieznosci' do plan_produkcji
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'wyjasnienie_rozbieznosci'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'wyjasnienie_rozbieznosci'...")
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN wyjasnienie_rozbieznosci TEXT")

        # Sprawdź i dodaj 'typ_produkcji' do plan_produkcji
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'typ_produkcji'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'typ_produkcji'...")
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN typ_produkcji VARCHAR(20) DEFAULT 'standard'")

        # Sprawdź i dodaj 'tara' do palety_workowanie
        cursor.execute("SHOW COLUMNS FROM palety_workowanie LIKE 'tara'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'tara' do palet...")
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN tara FLOAT DEFAULT 0")

        # Sprawdź i dodaj 'waga_brutto' do palety_workowanie
        cursor.execute("SHOW COLUMNS FROM palety_workowanie LIKE 'waga_brutto'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'waga_brutto' do palet...")
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN waga_brutto FLOAT DEFAULT 0")

        # 3. DODANIE DOMYŚLNYCH KONT (Jeśli brak) - zapisujemy hasła zhaszowane
        cursor.execute("SELECT id, haslo FROM uzytkownicy")
        existing = cursor.fetchall()

        # Ensure 'grupa' column exists on users and employees for RBAC grouping
        cursor.execute("SHOW COLUMNS FROM uzytkownicy LIKE 'grupa'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'grupa' do uzytkownicy...")
            cursor.execute("ALTER TABLE uzytkownicy ADD COLUMN grupa VARCHAR(50) DEFAULT ''")

        cursor.execute("SHOW COLUMNS FROM pracownicy LIKE 'grupa'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'grupa' do pracownicy...")
            cursor.execute("ALTER TABLE pracownicy ADD COLUMN grupa VARCHAR(50) DEFAULT ''")

        # Jeśli tabela ma wpisy, spróbuj zidentyfikować i zhashować plaintext hasła
        migrated = 0
        for row in existing:
            uid, pwd = row[0], row[1]
            # Only migrate if the stored value does not look like a hash we already support.
            # Skip values that start with known hash prefixes (e.g., 'pbkdf2:', 'scrypt:').
            if pwd:
                s = str(pwd)
                if not (s.startswith('pbkdf2:') or s.startswith('scrypt:') or s.startswith('sha1:')):
                    # Treat as plaintext and hash it using PBKDF2-SHA256
                    new_h = generate_password_hash(s, method='pbkdf2:sha256')
                    cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE id=%s", (new_h, uid))
                    migrated += 1
        if migrated:
            print(f"🔐 Zhashowano {migrated} istniejących haseł użytkowników.")

        cursor.execute("SELECT id FROM uzytkownicy WHERE login='admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('admin', generate_password_hash('masterkey', method='pbkdf2:sha256'), 'admin'))

        cursor.execute("SELECT id FROM uzytkownicy WHERE login='planista'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('planista', generate_password_hash('planista123', method='pbkdf2:sha256'), 'planista'))

        conn.commit()
        conn.close()
        print("✅ Baza danych zaktualizowana pomyślnie.")
        
    except Exception as e:
        print(f"❌ BŁĄD KRYTYCZNY BAZY DANYCH: {e}")