import mysql.connector
import logging
from config import DB_CONFIG

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG, buffered=True)

def setup_database():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Tabela UŻYTKOWNICY
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uzytkownicy (
                id INT AUTO_INCREMENT PRIMARY KEY,
                login VARCHAR(50) NOT NULL UNIQUE,
                haslo VARCHAR(100) NOT NULL,
                rola VARCHAR(20) NOT NULL
            )
        """)

        # 2. Tabela PRACOWNICY
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pracownicy (
                id INT AUTO_INCREMENT PRIMARY KEY,
                imie_nazwisko VARCHAR(100) NOT NULL
            )
        """)

        # 3. Tabela PLAN PRODUKCJI
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
                kolejnosc INT DEFAULT 0
            )
        """)

        # 4. Tabela DZIENNIK ZMIANY (Awarie/Przestoje)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dziennik_zmiany (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_wpisu DATE NOT NULL,
                sekcja VARCHAR(50),
                problem TEXT,
                czas_start DATETIME,
                czas_stop DATETIME,
                status VARCHAR(20) DEFAULT 'roboczy',
                kategoria VARCHAR(50) NULL,
                pracownik_id INT
            )
        """)

        # 5. Tabela OBSADA ZMIANY
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS obsada_zmiany (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_wpisu DATE NOT NULL,
                sekcja VARCHAR(50),
                pracownik_id INT,
                FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE
            )
        """)

        # 6. Tabela OBECNOŚĆ (HR)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS obecnosc (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_wpisu DATE NOT NULL,
                pracownik_id INT,
                typ VARCHAR(50),
                ilosc_godzin FLOAT DEFAULT 0,
                komentarz TEXT,
                FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE
            )
        """)

        # 7. Tabela PALETY (Workowanie)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS palety_workowanie (
                id INT AUTO_INCREMENT PRIMARY KEY,
                plan_id INT,
                waga FLOAT NOT NULL,
                data_dodania DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE
            )
        """)

        # 8. Tabela RAPORTY KOŃCOWE (Uwagi lidera)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raporty_koncowe (
                id INT AUTO_INCREMENT PRIMARY KEY,
                data_raportu DATE NOT NULL,
                lider_uwagi TEXT
            )
        """)

        # --- SEKCJA AUTOMATYCZNYCH MIGRACJI I NAPRAW ---
        
        # Dodanie domyślnego Admina i Planisty (jeśli nie istnieją)
        cursor.execute("SELECT id FROM uzytkownicy WHERE login='admin'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES ('admin', 'admin123', 'admin')")
            print("🔧 Dodano użytkownika: admin")

        cursor.execute("SELECT id FROM uzytkownicy WHERE login='planista'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES ('planista', 'planista123', 'planista')")
            print("🔧 Dodano użytkownika: planista")

        # Migracja 1: Dodanie kategorii do dziennika (jeśli brakuje)
        try:
            cursor.execute("ALTER TABLE dziennik_zmiany ADD COLUMN kategoria VARCHAR(50) NULL")
            print("🔧 Baza zaktualizowana: dodano kolumnę 'kategoria'")
        except:
            pass

        # Migracja 2: Dodanie kolejności do planu (DLA PLANISTY)
        try:
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN kolejnosc INT DEFAULT 0")
            print("🔧 Baza zaktualizowana: dodano kolumnę 'kolejnosc'")
            # Uzupełnienie zerami, żeby sortowanie działało od razu
            cursor.execute("UPDATE plan_produkcji SET kolejnosc = id WHERE kolejnosc IS NULL")
        except:
            pass

        conn.commit()
        conn.close()
        
    except Exception as e:
        error_msg = f"KRYTYCZNY BŁĄD BAZY DANYCH: {e}"
        print(error_msg)
        logging.error(error_msg)

def rollover_unfinished(from_date, to_date):
    """
    Przenosi niezakończone zlecenia z from_date na to_date.
    Dotyczy statusów innych niż 'zakonczone' (czyli 'zaplanowane', 'w toku', 'nieoplacone').
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Logika: Kopiuj wszystko co NIE jest zakończone
        # Sprawdzamy duplikaty, aby nie powielić zlecenia jeśli skrypt odpali się 2 razy
        cur.execute("""
            INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, kolejnosc)
            SELECT %s, p.sekcja, p.produkt, p.tonaz, 
                   CASE WHEN p.status = 'w toku' THEN 'zaplanowane' ELSE p.status END,
                   p.kolejnosc
            FROM plan_produkcji p
            WHERE p.data_planu = %s 
              AND COALESCE(p.status, '') != 'zakonczone'
              AND NOT EXISTS (
                SELECT 1 FROM plan_produkcji p2
                WHERE p2.data_planu = %s
                  AND p2.sekcja = p.sekcja
                  AND p2.produkt = p.produkt
                  AND (p2.tonaz = p.tonaz OR (p2.tonaz IS NULL AND p.tonaz IS NULL))
              )
        """, (to_date, from_date, to_date))
        
        added = cur.rowcount
        conn.commit()
        conn.close()
        return added
    except Exception as e:
        print(f"Błąd przy rollover: {e}")
        logging.error(f"Błąd rollover: {e}")
        try:
            conn.close()
        except:
            pass
        return 0