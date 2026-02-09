import mysql.connector
from app.config import DB_CONFIG
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

def _create_tables(cursor):
    """Create all base tables if they don't exist."""
    cursor.execute("CREATE TABLE IF NOT EXISTS uzytkownicy (id INT AUTO_INCREMENT PRIMARY KEY, login VARCHAR(50) UNIQUE, haslo VARCHAR(255), rola VARCHAR(20))")
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
    
    cursor.execute("CREATE TABLE IF NOT EXISTS dziennik_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), problem TEXT, czas_start DATETIME, czas_stop DATETIME, status VARCHAR(30) DEFAULT 'zgłoszone', kategoria VARCHAR(50), pracownik_id INT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS obsada_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), pracownik_id INT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS obsada_liderzy (data_wpisu DATE PRIMARY KEY, lider_psd_id INT NULL, lider_agro_id INT NULL, FOREIGN KEY (lider_psd_id) REFERENCES pracownicy(id) ON DELETE SET NULL, FOREIGN KEY (lider_agro_id) REFERENCES pracownicy(id) ON DELETE SET NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS obecnosc (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, pracownik_id INT, typ VARCHAR(50), ilosc_godzin FLOAT DEFAULT 0, komentarz TEXT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS wnioski_wolne (id INT AUTO_INCREMENT PRIMARY KEY, pracownik_id INT NOT NULL, typ VARCHAR(50) NOT NULL, data_od DATE NOT NULL, data_do DATE NOT NULL, czas_od TIME NULL, czas_do TIME NULL, powod TEXT, status VARCHAR(20) DEFAULT 'pending', zlozono DATETIME DEFAULT CURRENT_TIMESTAMP, decyzja_dnia DATETIME NULL, lider_id INT NULL, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS raporty_koncowe (id INT AUTO_INCREMENT PRIMARY KEY, data_raportu DATE, sekcja VARCHAR(50), lider_id INT, lider_uwagi TEXT, summary_json LONGTEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (lider_id) REFERENCES pracownicy(id) ON DELETE SET NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS plan_history (id INT AUTO_INCREMENT PRIMARY KEY, plan_id INT NULL, action VARCHAR(50), changes LONGTEXT, user_login VARCHAR(100), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS szarze (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT NOT NULL,
            waga FLOAT NOT NULL,
            data_dodania DATETIME DEFAULT CURRENT_TIMESTAMP,
            godzina TIME,
            pracownik_id INT,
            status VARCHAR(20) DEFAULT 'zarejestowana',
            uwagi TEXT,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE,
            FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE SET NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dziennik_zmian_statusu (
            id INT AUTO_INCREMENT PRIMARY KEY,
            awaria_id INT NOT NULL,
            stary_status VARCHAR(30),
            nowy_status VARCHAR(30) NOT NULL,
            zmieniony_przez INT,
            data_zmiany DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (awaria_id) REFERENCES dziennik_zmiany(id) ON DELETE CASCADE,
            FOREIGN KEY (zmieniony_przez) REFERENCES pracownicy(id) ON DELETE SET NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bufor (
            id INT AUTO_INCREMENT PRIMARY KEY,
            zasyp_id INT NOT NULL,
            data_planu DATE NOT NULL,
            produkt VARCHAR(100) NOT NULL,
            nazwa_zlecenia VARCHAR(255) DEFAULT '',
            typ_produkcji VARCHAR(20) DEFAULT 'worki_zgrzewane_25',
            tonaz_rzeczywisty FLOAT DEFAULT 0,
            spakowano FLOAT DEFAULT 0,
            kolejka INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'aktywny',
            UNIQUE KEY `bufor_uq_data_produkt_kolejka` (data_planu, produkt, kolejka),
            FOREIGN KEY (zasyp_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE
        )
    """)


def _add_column_if_missing(cursor, table, column, definition, description=""):
    """Helper to add column if it doesn't exist."""
    cursor.execute(f"SHOW COLUMNS FROM {table} LIKE '{column}'")
    if not cursor.fetchone():
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            if description:
                print(f"[MIGRATE] {description}")
        except Exception as e:
            print(f"[WARN] Nie udało się dodać kolumny {table}.{column}: {e}")
            pass


def _migrate_columns(cursor):
    """Add missing columns to existing tables (schema migrations)."""
    # plan_produkcji columns
    _add_column_if_missing(cursor, "plan_produkcji", "typ_produkcji", "VARCHAR(20) DEFAULT 'worki_zgrzewane_25'", "Dodawanie kolumny 'typ_produkcji'")
    _add_column_if_missing(cursor, "plan_produkcji", "nazwa_zlecenia", "VARCHAR(255) DEFAULT ''", "Dodawanie kolumny 'nazwa_zlecenia'")
    _add_column_if_missing(cursor, "plan_produkcji", "typ_zlecenia", "VARCHAR(50) DEFAULT ''", "Dodawanie kolumny 'typ_zlecenia'")
    _add_column_if_missing(cursor, "plan_produkcji", "nr_receptury", "VARCHAR(64) DEFAULT ''", "Dodawanie kolumny 'nr_receptury'")
    _add_column_if_missing(cursor, "plan_produkcji", "uszkodzone_worki", "INT DEFAULT 0", "Dodawanie kolumny 'uszkodzone_worki'")
    _add_column_if_missing(cursor, "plan_produkcji", "is_deleted", "BOOLEAN DEFAULT 0", "Dodawanie kolumny 'is_deleted' dla soft delete")
    _add_column_if_missing(cursor, "plan_produkcji", "deleted_at", "DATETIME NULL", "Dodawanie kolumny 'deleted_at' dla soft delete")
    
    # Update typ_zlecenia for known quality orders
    try:
        cursor.execute("UPDATE plan_produkcji SET typ_zlecenia='jakosc' WHERE LOWER(TRIM(produkt)) IN ('dezynfekcja linii','dezynfekcja')")
    except Exception:
        pass
    
    # palety_workowanie columns
    _add_column_if_missing(cursor, "palety_workowanie", "tara", "FLOAT DEFAULT 0", "Dodawanie kolumny 'tara' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "waga_brutto", "FLOAT DEFAULT 0", "Dodawanie kolumny 'waga_brutto' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "status", "VARCHAR(20) DEFAULT 'do_przyjecia'", "Dodawanie kolumny 'status' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "data_potwierdzenia", "DATETIME NULL", "Dodawanie kolumny 'data_potwierdzenia' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "czas_potwierdzenia_s", "INT NULL", "Dodawanie kolumny 'czas_potwierdzenia_s' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "czas_rzeczywistego_potwierdzenia", "TIME NULL", "Dodawanie kolumny 'czas_rzeczywistego_potwierdzenia' do palet")
    
    # raporty_koncowe columns
    _add_column_if_missing(cursor, "raporty_koncowe", "sekcja", "VARCHAR(50)", "Dodawanie kolumny 'sekcja' do raporty_koncowe")
    _add_column_if_missing(cursor, "raporty_koncowe", "lider_id", "INT", "Dodawanie kolumny 'lider_id' do raporty_koncowe")
    _add_column_if_missing(cursor, "raporty_koncowe", "summary_json", "LONGTEXT", "Dodawanie kolumny 'summary_json' do raporty_koncowe")
    _add_column_if_missing(cursor, "raporty_koncowe", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'created_at' do raporty_koncowe")
    
    # dziennik_zmiany (awarii) columns
    # _add_column_if_missing(cursor, "dziennik_zmiany", "status_zglosnienia", "VARCHAR(30) DEFAULT 'zgłoszony'", "Dodawanie kolumny 'status_zglosnienia' do dziennik_zmiany")  # DEPRECATED: Using single 'status' field instead
    _add_column_if_missing(cursor, "dziennik_zmiany", "data_zakonczenia", "DATE NULL", "Dodawanie kolumny 'data_zakonczenia' do dziennik_zmiany")
    
    # user/employee columns
    _add_column_if_missing(cursor, "uzytkownicy", "grupa", "VARCHAR(50) DEFAULT ''", "Dodawanie kolumny 'grupa' do uzytkownicy")
    _add_column_if_missing(cursor, "pracownicy", "grupa", "VARCHAR(50) DEFAULT ''", "Dodawanie kolumny 'grupa' do pracownicy")
    _add_column_if_missing(cursor, "uzytkownicy", "pracownik_id", "INT NULL", "Dodawanie kolumny 'pracownik_id' do uzytkownicy")


def _seed_default_users(cursor):
    """Create default users if they don't exist."""
    # Migrate plaintext passwords to hashed
    cursor.execute("SELECT id, haslo FROM uzytkownicy")
    existing = cursor.fetchall()
    
    migrated = 0
    for row in existing:
        uid, pwd = row[0], row[1]
        if pwd:
            s = str(pwd)
            if not (s.startswith('pbkdf2:') or s.startswith('scrypt:') or s.startswith('sha1:')):
                new_h = generate_password_hash(s, method='pbkdf2:sha256')
                cursor.execute("UPDATE uzytkownicy SET haslo=%s WHERE id=%s", (new_h, uid))
                migrated += 1
    
    if migrated:
        print(f"🔐 Zhashowano {migrated} istniejących haseł użytkowników.")
    
    # Create default admin account if needed
    cursor.execute("SELECT id FROM uzytkownicy WHERE login='admin'")
    if not cursor.fetchone():
        init_pass = os.environ.get('INITIAL_ADMIN_PASSWORD')
        if init_pass:
            cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('admin', generate_password_hash(init_pass, method='pbkdf2:sha256'), 'admin'))
        else:
            print("[SECURITY] No INITIAL_ADMIN_PASSWORD provided; skipping creation of default 'admin' account.")
    
    # Create default planista account
    cursor.execute("SELECT id FROM uzytkownicy WHERE login='planista'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO uzytkownicy (login, haslo, rola) VALUES (%s, %s, %s)", ('planista', generate_password_hash('planista123', method='pbkdf2:sha256'), 'planista'))


def refresh_bufor_queue(conn=None):
    """Odświeța bufor - dodaje nowe zlecenia z przepisanymi kolejkami"""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    try:
        cursor = conn.cursor()
        
        # SYNC 1: Synchronizuj Workowanie.tonaz = Zasyp.tonaz_rzeczywisty (dla dzisiaj)
        try:
            cursor.execute("""
                UPDATE plan_produkcji w
                SET w.tonaz = (
                    SELECT COALESCE(z.tonaz_rzeczywisty, 0) FROM plan_produkcji z
                    WHERE z.sekcja = 'Zasyp' 
                    AND z.produkt = w.produkt 
                    AND DATE(z.data_planu) = DATE(w.data_planu)
                    ORDER BY COALESCE(z.real_stop, z.real_start, z.id) ASC
                    LIMIT 1
                )
                WHERE w.sekcja = 'Workowanie' AND DATE(w.data_planu) = CURDATE()
            """)
            if cursor.rowcount > 0:
                print(f"[SYNC] Workowanie.tonaz synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz failed: {e}")
        
        # SYNC 2: Synchronizuj Workowanie.tonaz_rzeczywisty = sum palet (dla dzisiaj)
        try:
            cursor.execute("""
                UPDATE plan_produkcji w
                SET w.tonaz_rzeczywisty = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM palety_workowanie pw
                    WHERE pw.plan_id = w.id
                )
                WHERE w.sekcja = 'Workowanie' AND DATE(w.data_planu) = CURDATE()
            """)
            if cursor.rowcount > 0:
                print(f"[SYNC] Workowanie.tonaz_rzeczywisty synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz_rzeczywisty failed: {e}")
        
        # 1. Usuń wszystkie wpisy z bufora dla Workowania które już się nie mają statusu 'w toku'
        cursor.execute("""
            DELETE FROM bufor 
            WHERE status = 'aktywny'
            AND NOT EXISTS (
                SELECT 1 FROM plan_produkcji w 
                WHERE w.sekcja = 'Workowanie' 
                AND w.status = 'w toku'
                AND w.produkt = bufor.produkt 
                AND w.data_planu = bufor.data_planu
            )
        """)
        deleted = cursor.rowcount
        
        # 2. Pobierz wszystkie Zasypy które powinny być w buforze
        # Warunki: wszystkie Zasypy (w toku, zakonczone) które mają odpowiadające Workowanie w statusie 'w toku' lub 'zaplanowane'
        # WAŻNE: Sortuj po real_start (czas rzeczywistego startu) aby kolejka bufor odzwierciedlała rzeczywistą kolejność startu
        cursor.execute("""
            SELECT z.id, z.data_planu, z.produkt, z.nazwa_zlecenia, z.typ_produkcji, 
                   z.tonaz_rzeczywisty, z.status
            FROM plan_produkcji z
            INNER JOIN plan_produkcji w ON z.produkt = w.produkt AND z.data_planu = w.data_planu
            WHERE z.sekcja = 'Zasyp'
              AND w.sekcja = 'Workowanie'
              AND w.status IN ('w toku', 'zaplanowane')
              AND (z.status = 'w toku' OR z.status = 'zakonczone')
              AND z.data_planu >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
              AND z.data_planu <= CURDATE()
              AND z.tonaz_rzeczywisty > 0
            ORDER BY z.data_planu DESC, CASE WHEN z.real_start IS NOT NULL THEN 0 ELSE 1 END ASC, 
                     z.real_start ASC, z.id ASC
        """)
        
        zasypy_do_bufora = cursor.fetchall()
        
        # 3. Dla każdego Zasypu - jeśli go nie ma w buforze, dodaj z nowym numerem kolejki
        added = 0
        for z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_status in zasypy_do_bufora:
            # Sprawdź czy już jest w buforze
            cursor.execute("""
                SELECT id FROM bufor 
                WHERE zasyp_id = %s AND status = 'aktywny'
            """, (z_id,))
            
            if not cursor.fetchone():
                # Nie ma - pobierz następny numer kolejki dla całej DATY (niezależnie od produktu)
                cursor.execute("""
                    SELECT MAX(kolejka) FROM bufor 
                    WHERE data_planu = %s AND status = 'aktywny'
                """, (z_data,))
                
                result = cursor.fetchone()
                next_kolejka = (result[0] or 0) + 1
                
                # Pobierz ile palet już spakowano
                cursor.execute("""
                    SELECT COALESCE(SUM(waga), 0) FROM palety_workowanie pw
                    INNER JOIN plan_produkcji w ON pw.plan_id = w.id
                    WHERE w.data_planu = %s AND w.produkt = %s AND w.sekcja = 'Workowanie'
                """, (z_data, z_produkt))
                
                spakowano_result = cursor.fetchone()
                spakowano = spakowano_result[0] if spakowano_result else 0
                
                # Dodaj do bufora
                cursor.execute("""
                    INSERT INTO bufor 
                    (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji, tonaz_rzeczywisty, spakowano, kolejka, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'aktywny')
                """, (z_id, z_data, z_produkt, z_nazwa or '', z_typ or 'worki_zgrzewane_25', 
                      z_tonaz, spakowano, next_kolejka))
                
                added += 1
        
        # WAŻNE: ZAWSZE Renumeruj kolejki żeby były Sequential (1,2,3,4...)
        # Po DELETE i po dodaniu nowych wpisów - renumeric: dzisiejsze najpierw (DESC), potem po real_start
        cursor.execute("""
            SELECT b.id, b.data_planu FROM bufor b
            LEFT JOIN plan_produkcji z ON z.id = b.zasyp_id
            WHERE b.status = 'aktywny'
            ORDER BY b.data_planu DESC, CASE WHEN z.real_start IS NOT NULL THEN 0 ELSE 1 END ASC, 
                     z.real_start ASC, b.id ASC
        """)
        bufor_entries = cursor.fetchall()
        for idx, (buf_id, buf_date) in enumerate(bufor_entries, start=1):
            cursor.execute("""
                UPDATE bufor SET kolejka = %s WHERE id = %s
            """, (idx, buf_id))
        
        # 4. Aktualizuj pola spakowano dla istniejących wpisów w buforze
        cursor.execute("""
            UPDATE bufor b
            SET spakowano = (
                SELECT COALESCE(SUM(pw.waga), 0) FROM palety_workowanie pw
                INNER JOIN plan_produkcji w ON pw.plan_id = w.id
                WHERE w.data_planu = b.data_planu AND w.produkt = b.produkt 
                AND w.sekcja = 'Workowanie'
            )
            WHERE status = 'aktywny'
        """)
        
        conn.commit()
        print(f"[BUFOR] Odświeżono bufor: usunięto {deleted}, dodano {added}")
        
    except Exception as e:
        print(f"[ERROR] refresh_bufor_queue: {e}")
        conn.rollback()
        raise
    finally:
        if close_conn:
            cursor.close()
            conn.close()


def _auto_confirm_existing_palety(cursor):
    """Auto-confirm all existing palety with data_dodania and set confirmation time to +2 minutes."""
    try:
        # Update all palety that have data_dodania but haven't been confirmed yet
        # Set: status='przyjeta', czas_rzeczywistego_potwierdzenia = TIME(data_dodania + 2 min), data_potwierdzenia=NOW()
        cursor.execute("""
            UPDATE palety_workowanie 
            SET 
                status = 'przyjeta',
                czas_rzeczywistego_potwierdzenia = TIME(DATE_ADD(data_dodania, INTERVAL 2 MINUTE)),
                data_potwierdzenia = NOW(),
                czas_potwierdzenia_s = TIMESTAMPDIFF(SECOND, data_dodania, NOW())
            WHERE 
                data_dodania IS NOT NULL 
                AND (status IS NULL OR status = 'do_przyjecia' OR czas_rzeczywistego_potwierdzenia IS NULL)
        """)
        affected = cursor.rowcount
        if affected > 0:
            print(f"[OK] Auto-confirmed {affected} existing palety (set confirmation time to +2 min)")
    except Exception as e:
        print(f"[INFO] Auto-confirm migration skipped or already applied: {e}")


def setup_database():
    """Main setup function - orchestrates all database initialization."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Create all base tables
        _create_tables(cursor)
        
        # 2. Run migrations (add missing columns)
        _migrate_columns(cursor)
        
        # 3. Seed default users (including password migration)
        _seed_default_users(cursor)
        
        # 4. Auto-confirm all palety with data_dodania and set confirmation time to +2 min
        _auto_confirm_existing_palety(cursor)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("[OK] Baza danych jest gotowa!")
        
        # 5. Odśwież bufor (wymagane połączenie)  
        refresh_bufor_queue()
        
    except Exception as e:
        print(f"[ERROR] Blad podczas inicjalizacji bazy danych: {e}")
        raise


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