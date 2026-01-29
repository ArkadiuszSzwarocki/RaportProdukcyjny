import mysql.connector
from config import DB_CONFIG
import os
from werkzeug.security import generate_password_hash
import time

def get_db_connection(retries=3):
    """Get database connection with retry logic"""
    last_error = None
    for attempt in range(retries):
        try:
            return mysql.connector.connect(**DB_CONFIG, buffered=True)
        except mysql.connector.Error as e:
            last_error = e
            if attempt < retries - 1:
                # Wait before retrying (exponential backoff)
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            continue
    # If all retries failed, raise the last error
    raise last_error

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
                typ_produkcji VARCHAR(20) DEFAULT 'worki_zgrzewane_25',
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
        # tabela przechowująca liderów przypisanych do obsady dla konkretnego dnia
        cursor.execute("CREATE TABLE IF NOT EXISTS obsada_liderzy (data_wpisu DATE PRIMARY KEY, lider_psd_id INT NULL, lider_agro_id INT NULL, FOREIGN KEY (lider_psd_id) REFERENCES pracownicy(id) ON DELETE SET NULL, FOREIGN KEY (lider_agro_id) REFERENCES pracownicy(id) ON DELETE SET NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS obecnosc (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, pracownik_id INT, typ VARCHAR(50), ilosc_godzin FLOAT DEFAULT 0, komentarz TEXT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
        # Tabela wniosków o wolne/prośby pracownicze
        cursor.execute("CREATE TABLE IF NOT EXISTS wnioski_wolne (id INT AUTO_INCREMENT PRIMARY KEY, pracownik_id INT NOT NULL, typ VARCHAR(50) NOT NULL, data_od DATE NOT NULL, data_do DATE NOT NULL, czas_od TIME NULL, czas_do TIME NULL, powod TEXT, status VARCHAR(20) DEFAULT 'pending', zlozono DATETIME DEFAULT CURRENT_TIMESTAMP, decyzja_dnia DATETIME NULL, lider_id INT NULL, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS raporty_koncowe (id INT AUTO_INCREMENT PRIMARY KEY, data_raportu DATE, sekcja VARCHAR(50), lider_id INT, lider_uwagi TEXT, summary_json LONGTEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (lider_id) REFERENCES pracownicy(id) ON DELETE SET NULL)")

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
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN typ_produkcji VARCHAR(20) DEFAULT 'worki_zgrzewane_25'")

        # Sprawdź i dodaj 'nazwa_zlecenia' do plan_produkcji (dla łatwiejszego czytania)
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'nazwa_zlecenia'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'nazwa_zlecenia' do plan_produkcji...")
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN nazwa_zlecenia VARCHAR(255) DEFAULT ''")

        # Sprawdź i dodaj 'typ_zlecenia' do plan_produkcji (np. 'jakosc' dla zlecen jakościowych)
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'typ_zlecenia'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'typ_zlecenia' do plan_produkcji...")
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN typ_zlecenia VARCHAR(50) DEFAULT ''")
            # Zaktualizuj istniejące rekordy rozpoznane jako dezynfekcja
            try:
                cursor.execute("UPDATE plan_produkcji SET typ_zlecenia='jakosc' WHERE LOWER(TRIM(produkt)) IN ('dezynfekcja linii','dezynfekcja')")
            except Exception:
                pass

        # Sprawdź i dodaj 'nr_receptury' do plan_produkcji (numer receptury)
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'nr_receptury'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'nr_receptury' do plan_produkcji...")
            try:
                cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN nr_receptury VARCHAR(64) DEFAULT ''")
            except Exception:
                pass

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

        # Sprawdź i dodaj 'status' (do_przyjecia / przyjeta / zamknieta) do palety_workowanie
        cursor.execute("SHOW COLUMNS FROM palety_workowanie LIKE 'status'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'status' do palet...")
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN status VARCHAR(20) DEFAULT 'do_przyjecia'")

        # Sprawdź i dodaj 'data_potwierdzenia' (czas zatwierdzenia) do palety_workowanie
        cursor.execute("SHOW COLUMNS FROM palety_workowanie LIKE 'data_potwierdzenia'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'data_potwierdzenia' do palet...")
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN data_potwierdzenia DATETIME NULL")

        # Sprawdź i dodaj 'czas_potwierdzenia_s' (gotowy czas w sekundach) do palety_workowanie
        cursor.execute("SHOW COLUMNS FROM palety_workowanie LIKE 'czas_potwierdzenia_s'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'czas_potwierdzenia_s' do palet...")
            cursor.execute("ALTER TABLE palety_workowanie ADD COLUMN czas_potwierdzenia_s INT NULL")

        # Sprawdzić i rozszerzyć tabelę raporty_koncowe
        cursor.execute("SHOW COLUMNS FROM raporty_koncowe LIKE 'sekcja'")
        if not cursor.fetchone():
            print("⏳ Rozszerzanie tabeli raporty_koncowe...")
            try:
                cursor.execute("ALTER TABLE raporty_koncowe ADD COLUMN sekcja VARCHAR(50)")
            except Exception:
                pass
        
        cursor.execute("SHOW COLUMNS FROM raporty_koncowe LIKE 'lider_id'")
        if not cursor.fetchone():
            try:
                cursor.execute("ALTER TABLE raporty_koncowe ADD COLUMN lider_id INT")
            except Exception:
                pass
        
        cursor.execute("SHOW COLUMNS FROM raporty_koncowe LIKE 'summary_json'")
        if not cursor.fetchone():
            try:
                cursor.execute("ALTER TABLE raporty_koncowe ADD COLUMN summary_json LONGTEXT")
            except Exception:
                pass

        cursor.execute("SHOW COLUMNS FROM raporty_koncowe LIKE 'created_at'")
        if not cursor.fetchone():
            try:
                cursor.execute("ALTER TABLE raporty_koncowe ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            except Exception:
                pass

        # Tabela historii zmian planu
        cursor.execute("CREATE TABLE IF NOT EXISTS plan_history (id INT AUTO_INCREMENT PRIMARY KEY, plan_id INT NULL, action VARCHAR(50), changes LONGTEXT, user_login VARCHAR(100), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")

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

        # Sprawdź i dodaj 'pracownik_id' do uzytkownicy (mapowanie konta -> pracownik)
        cursor.execute("SHOW COLUMNS FROM uzytkownicy LIKE 'pracownik_id'")
        if not cursor.fetchone():
            print("⏳ Dodawanie kolumny 'pracownik_id' do uzytkownicy...")
            try:
                cursor.execute("ALTER TABLE uzytkownicy ADD COLUMN pracownik_id INT NULL")
            except Exception:
                # If DB user lacks permissions or older server, ignore — migrations handle this
                pass

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
            # Do not create a hard-coded default admin password in production.
            # Require INITIAL_ADMIN_PASSWORD environment variable to provision initial admin.
            init_pass = os.environ.get('INITIAL_ADMIN_PASSWORD')
            if init_pass:
                cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('admin', generate_password_hash(init_pass, method='pbkdf2:sha256'), 'admin'))
            else:
                print("[SECURITY] No INITIAL_ADMIN_PASSWORD provided; skipping creation of default 'admin' account.")

        cursor.execute("SELECT id FROM uzytkownicy WHERE login='planista'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('planista', generate_password_hash('planista123', method='pbkdf2:sha256'), 'planista'))

        # TABELA DLA KOMENTARZY DUR DO AWARII
        cursor.execute("SHOW COLUMNS FROM dziennik_zmiany LIKE 'czas_stop'")
        czas_stop_exists = cursor.fetchone()
        
        # Tabel dla komentarzy
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dur_komentarze (
                id INT AUTO_INCREMENT PRIMARY KEY,
                awaria_id INT NOT NULL,
                autor_id INT,
                tresc TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (awaria_id) REFERENCES dziennik_zmiany(id) ON DELETE CASCADE,
                FOREIGN KEY (autor_id) REFERENCES pracownicy(id) ON DELETE SET NULL
            )
        """)
        print("[OK] Tabela dur_komentarze istnieje/została utworzona")

        conn.commit()
        conn.close()
        print("[OK] Baza danych zaktualizowana pomyslnie.")
        
    except Exception as e:
        print(f"[ERROR] BLAD KRYTYCZNY BAZY DANYCH: {e}")


def rollover_unfinished(from_date, to_date):
    """Przenosi niezakończone zlecenia z `from_date` na `to_date`.
    Zlecenia przenoszone są jako nowe wiersze z datą docelową, statusem
    'zaplanowane' (reset real_start/real_stop) i odpowiednią kolejnością.
    Oryginały są usuwane.
    Zwraca liczbę przeniesionych zleceń.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, sekcja, produkt, tonaz, status, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury FROM plan_produkcji WHERE data_planu=%s", (from_date,))
        rows = cursor.fetchall()
        moved = 0
        moved_ids = []
        for row in rows:
            pid, sekcja, produkt, tonaz, status, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury = row
            if status == 'zakonczone':
                continue

            # pobierz kolejność docelową
            cursor.execute("SELECT MAX(kolejnosc) FROM plan_produkcji WHERE data_planu=%s", (to_date,))
            res = cursor.fetchone()
            nk = (res[0] if res and res[0] else 0) + 1

            cursor.execute(
                "INSERT INTO plan_produkcji (data_planu, sekcja, produkt, tonaz, status, real_start, real_stop, tonaz_rzeczywisty, kolejnosc, typ_produkcji, nazwa_zlecenia, typ_zlecenia, nr_receptury) VALUES (%s, %s, %s, %s, 'zaplanowane', NULL, NULL, NULL, %s, %s, %s, %s, %s)",
                (to_date, sekcja, produkt, tonaz, nk, typ_produkcji or 'worki_zgrzewane_25', nazwa_zlecenia or '', typ_zlecenia or '', nr_receptury or '')
            )
            # usuń oryginał
            cursor.execute("DELETE FROM plan_produkcji WHERE id=%s", (pid,))
            moved += 1
            moved_ids.append(pid)
            try:
                print(f"[rollover] Przeniesiono id={pid} produkt={produkt} sekcja={sekcja} tonaz={tonaz}")
            except Exception:
                # ensure logging doesn't break rollover
                pass

        conn.commit()
        try:
            if moved_ids:
                print(f"[rollover] Podsumowanie: przeniesiono {moved} zlecen: {', '.join(str(i) for i in moved_ids)}")
            else:
                print("[rollover] Podsumowanie: brak zlecen do przeniesienia.")
        except Exception:
            pass
        return moved

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[ERROR] rollover_unfinished failed: {e}")
        return 0
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def log_plan_history(plan_id, action, changes, user_login=None):
    """Zapisuje wpis do tabeli `plan_history`.
    `changes` może być stringiem (np. JSON) opisującym co się zmieniło.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO plan_history (plan_id, action, changes, user_login) VALUES (%s, %s, %s, %s)", (plan_id, action, changes, user_login))
        conn.commit()
        try:
            conn.close()
        except Exception:
            pass
    except Exception:
        try:
            conn.close()
        except Exception:
            pass