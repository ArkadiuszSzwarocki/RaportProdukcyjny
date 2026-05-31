"""
Wersja: 1.1.0
Opis: Połączenie z bazą danych i funkcje pomocnicze. Obsługuje MySQL, nazewnictwo tabel i współdzielenie kursora.
"""
import mysql.connector
from app.config import DB_CONFIG, BUFOR_LOOKBACK_DAYS, BUFOR_LOOKAHEAD_DAYS
import os
from werkzeug.security import generate_password_hash
import time
import threading
from datetime import date, timedelta
import uuid

from app.db_tables import resolve_table_name

_DB_CONFIG_LOCK = threading.Lock()
_RUNTIME_SWITCHABLE_DATABASES = ('biblioteka', 'biblioteka_testowa', 'biblioteka_test')


def get_runtime_switchable_databases():
    """Return list of database names allowed for runtime switching."""
    return list(_RUNTIME_SWITCHABLE_DATABASES)


# Wykryj środowisko lokalne, aby git-owany active_db.txt nie nadpisywał lokalnej konfiguracji .env
is_local = (
    os.getenv('LOCAL_ENV', 'false').lower() == 'true' or
    os.getenv('IS_LOCAL', 'false').lower() == 'true' or
    os.getenv('FLASK_ENV', 'production').lower() == 'development'
)

if is_local:
    _DB_PERSISTENCE_FILE = os.path.join(os.getcwd(), 'active_db_local.txt')
else:
    _DB_PERSISTENCE_FILE = os.path.join(os.getcwd(), 'active_db.txt')

def _persist_database_name(name):
    try:
        with open(_DB_PERSISTENCE_FILE, 'w', encoding='utf-8') as f:
            f.write(name)
    except Exception:
        pass

def _load_persisted_database_name():
    if os.path.exists(_DB_PERSISTENCE_FILE):
        try:
            with open(_DB_PERSISTENCE_FILE, 'r', encoding='utf-8') as f:
                name = f.read().strip()
                if name in _RUNTIME_SWITCHABLE_DATABASES:
                    return name
        except Exception:
            pass
    return None

# Load persisted DB on module import.
# In CI/testing, environment variables must win over git-tracked active_db*.txt.
_persisted_db = _load_persisted_database_name()
_is_ci_env = str(os.getenv('CI', '')).lower() == 'true' or str(os.getenv('GITHUB_ACTIONS', '')).lower() == 'true'
_is_test_env = str(os.getenv('FLASK_ENV', '')).lower() == 'testing' or ('PYTEST_CURRENT_TEST' in os.environ)
if _persisted_db and not (_is_ci_env or _is_test_env):
    with _DB_CONFIG_LOCK:
        DB_CONFIG['database'] = _persisted_db

def get_active_database_name():
    """Return currently active database name from runtime config."""
    with _DB_CONFIG_LOCK:
        return str(DB_CONFIG.get('database') or '')

def set_active_database_name(database_name, verify_connection=True):
    """Switch active database used by get_db_connection.
    
    Raises:
        ValueError: when database is not allowed or empty.
        mysql.connector.Error: when test connection fails.
    """
    target_name = str(database_name or '').strip()
    if not target_name:
        raise ValueError('Nie podano nazwy bazy danych.')
    if target_name not in _RUNTIME_SWITCHABLE_DATABASES:
        raise ValueError(f'Baza {target_name} nie jest dozwolona do przełączania.')

    # Validate connectivity before mutating global runtime config.
    if verify_connection:
        with _DB_CONFIG_LOCK:
            test_config = dict(DB_CONFIG)
        test_config['database'] = target_name
        probe = mysql.connector.connect(**test_config, buffered=True)
        probe.close()

    with _DB_CONFIG_LOCK:
        DB_CONFIG['database'] = target_name
    
    _persist_database_name(target_name)
    
    # Automatically initialize / migrate tables in the newly active database!
    try:
        setup_database()
    except Exception as e:
        print(f"[WARN] Failed to setup database {target_name} on switch: {e}")
        
    return target_name

def get_db_connection(retries=3):
    """Get database connection with retry logic"""
    last_error = None
    for attempt in range(retries):
        try:
            with _DB_CONFIG_LOCK:
                conn_config = dict(DB_CONFIG)
            return mysql.connector.connect(**conn_config, buffered=True)
        except mysql.connector.Error as e:
            last_error = e
            if attempt < retries - 1:
                # Wait before retrying (exponential backoff)
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            continue
    # If all retries failed, raise the last error
    raise last_error

def get_table_name(base_table, linia='PSD'):
    """Return table name based on production line (PSD or AGRO)."""
    return resolve_table_name(base_table, linia)

def _create_tables(cursor):
    """Create all base tables if they don't exist."""
    cursor.execute("CREATE TABLE IF NOT EXISTS uzytkownicy (id INT AUTO_INCREMENT PRIMARY KEY, login VARCHAR(50) UNIQUE, haslo VARCHAR(255), rola VARCHAR(20))")
    try:
        cursor.execute("ALTER TABLE uzytkownicy MODIFY haslo VARCHAR(255)")
    except Exception:
        pass
        
    try:
        cursor.execute("ALTER TABLE uzytkownicy ADD COLUMN grupa VARCHAR(50) DEFAULT NULL")
    except Exception:
        pass
    
    cursor.execute("CREATE TABLE IF NOT EXISTS pracownicy (id INT AUTO_INCREMENT PRIMARY KEY, imie_nazwisko VARCHAR(100))")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zgloszenia_bledow (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_login VARCHAR(100),
            page_url VARCHAR(255),
            opis TEXT,
            status VARCHAR(20) DEFAULT 'nowe',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabela dla blokad stanowisk produkcyjnych AGRO
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agro_stanowiska (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(100) UNIQUE NOT NULL,
            typ VARCHAR(50),
            is_locked BOOLEAN DEFAULT 0,
            current_pallet_id INT NULL,
            current_plan_id INT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    
    # Inicjalizacja stacji jeśli puste
    cursor.execute("SELECT COUNT(*) FROM agro_stanowiska")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO agro_stanowiska (nazwa, typ) VALUES ('Parcianka (Big-Bag)', 'bigbag'), ('Zasyp Manualny', 'zasyp')")

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
            wyjasnienie_rozbieznosci TEXT,
            data_produkcji DATE DEFAULT NULL
        )
    """)

    # Tabela produkcyjna dla linii AGRO (analogiczna do plan_produkcji)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_produkcji_agro (
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
            typ_produkcji VARCHAR(20) DEFAULT 'agro',
            nazwa_zlecenia VARCHAR(255) DEFAULT '',
            typ_zlecenia VARCHAR(50) DEFAULT '',
            nr_receptury VARCHAR(64) DEFAULT '',
            zasyp_id INT NULL DEFAULT NULL,
            wyjasnienie_rozbieznosci TEXT,
            uszkodzone_worki INT DEFAULT 0,
            is_deleted BOOLEAN DEFAULT 0,
            deleted_at DATETIME NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            data_produkcji DATE DEFAULT NULL
        )
    """)

    # Tabela dla planowania AGRO (oddzielna od PSD/plan_produkcji)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plan_agro (
            id INT AUTO_INCREMENT PRIMARY KEY,
            data_planu DATE NOT NULL,
            produkt VARCHAR(100) NOT NULL,
            tonaz FLOAT,
            status VARCHAR(20) DEFAULT 'zaplanowane',
            real_start DATETIME,
            real_stop DATETIME,
            tonaz_rzeczywisty FLOAT,
            kolejnosc INT DEFAULT 0,
            typ_produkcji VARCHAR(50) DEFAULT 'agro',
            nr_receptury VARCHAR(64) DEFAULT '',
            nazwa_zlecenia VARCHAR(255) DEFAULT '',
            wyjasnienie_rozbieznosci TEXT,
            uszkodzone_worki INT DEFAULT 0,
            start_machine_counter INT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS palety_workowanie (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT,
            waga FLOAT,
            tara FLOAT DEFAULT 0,
            waga_brutto FLOAT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'do_przyjecia',
            dodal_login VARCHAR(100) DEFAULT NULL,
            data_dodania DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS palety_agro (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT,
            waga FLOAT,
            tara FLOAT DEFAULT 0,
            waga_brutto FLOAT DEFAULT 0,
            data_dodania DATETIME DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'do_przyjecia',
            dodal_login VARCHAR(100) DEFAULT NULL,
            data_potwierdzenia DATETIME NULL,
            czas_potwierdzenia_s INT NULL,
            czas_rzeczywistego_potwierdzenia TIME NULL,
            waga_potwierdzona FLOAT NULL,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji_agro(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_palety (
            id INT AUTO_INCREMENT PRIMARY KEY,
            paleta_workowanie_id INT NULL,
            plan_id INT NULL,
            data_planu DATE NULL,
            produkt VARCHAR(100) NULL,
            waga_netto FLOAT DEFAULT 0,
            waga_brutto FLOAT DEFAULT 0,
            tara FLOAT DEFAULT 0,
            user_login VARCHAR(100) DEFAULT NULL,
            data_potwierdzenia DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paleta_workowanie_id) REFERENCES palety_workowanie(id) ON DELETE SET NULL,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_palety_agro (
            id INT AUTO_INCREMENT PRIMARY KEY,
            paleta_workowanie_id INT NULL,
            plan_id INT NULL,
            data_planu DATE NULL,
            produkt VARCHAR(100) NULL,
            waga_netto FLOAT DEFAULT 0,
            waga_brutto FLOAT DEFAULT 0,
            tara FLOAT DEFAULT 0,
            user_login VARCHAR(100) DEFAULT NULL,
            data_potwierdzenia DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (paleta_workowanie_id) REFERENCES palety_agro(id) ON DELETE SET NULL,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji_agro(id) ON DELETE SET NULL
        )
    """)
    
    cursor.execute("CREATE TABLE IF NOT EXISTS dziennik_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), problem TEXT, czas_start DATETIME, czas_stop DATETIME, status VARCHAR(30) DEFAULT 'zgłoszone', kategoria VARCHAR(50), pracownik_id INT)")

    # Tabela historii ruchów palet (traceability)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS palety_historia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            paleta_id INT NULL,
            linia VARCHAR(20) NOT NULL,
            typ_palety VARCHAR(50) DEFAULT 'wyrob_gotowy',
            akcja VARCHAR(50) NOT NULL,
            lokalizacja_zrodlowa VARCHAR(100) NULL,
            lokalizacja_docelowa VARCHAR(100) NULL,
            komentarz TEXT NULL,
            user_login VARCHAR(100) NULL,
            data_ruchu DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_surowce (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(255) NOT NULL,
            stan_magazynowy FLOAT DEFAULT 0,
            lokalizacja VARCHAR(64) DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_magazyn_surowce_nazwa (nazwa(250)),
            INDEX idx_magazyn_surowce_lokal (lokalizacja)
        )
    """)

    cursor.execute("CREATE TABLE IF NOT EXISTS magazyn_opakowania ("
                   "id INT AUTO_INCREMENT PRIMARY KEY,"
                   "nazwa VARCHAR(255) NOT NULL,"
                   "stan_magazynowy FLOAT DEFAULT 0,"
                   "lokalizacja VARCHAR(64) DEFAULT NULL,"
                   "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                   "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                   "INDEX idx_magazyn_opakowania_nazwa (nazwa(250)),"
                   "INDEX idx_magazyn_opakowania_lokal (lokalizacja)"
                   ")")

    # magazyn_agro_surowce and magazyn_agro_opakowania are now unified into the primary tables
    cursor.execute("CREATE TABLE IF NOT EXISTS obsada_zmiany (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, sekcja VARCHAR(50), pracownik_id INT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS obsada_liderzy (data_wpisu DATE PRIMARY KEY, lider_psd_id INT NULL, lider_agro_id INT NULL, FOREIGN KEY (lider_psd_id) REFERENCES pracownicy(id) ON DELETE SET NULL, FOREIGN KEY (lider_agro_id) REFERENCES pracownicy(id) ON DELETE SET NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS obecnosc (id INT AUTO_INCREMENT PRIMARY KEY, data_wpisu DATE, pracownik_id INT, typ VARCHAR(50), ilosc_godzin FLOAT DEFAULT 0, komentarz TEXT, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS wnioski_wolne (id INT AUTO_INCREMENT PRIMARY KEY, pracownik_id INT NOT NULL, typ VARCHAR(50) NOT NULL, data_od DATE NOT NULL, data_do DATE NOT NULL, czas_od TIME NULL, czas_do TIME NULL, powod TEXT, status VARCHAR(20) DEFAULT 'pending', zlozono DATETIME DEFAULT CURRENT_TIMESTAMP, decyzja_dnia DATETIME NULL, lider_id INT NULL, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
    cursor.execute("CREATE TABLE IF NOT EXISTS nadgodziny (id INT AUTO_INCREMENT PRIMARY KEY, pracownik_id INT NOT NULL, data DATE NOT NULL, ilosc_nadgodzin FLOAT NOT NULL, powod TEXT, status VARCHAR(20) DEFAULT 'pending', zlozono DATETIME DEFAULT CURRENT_TIMESTAMP, decyzja_dnia DATETIME NULL, lider_id INT NULL, FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE CASCADE)")
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
        CREATE TABLE IF NOT EXISTS dosypki (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT NOT NULL,
            szarza_id INT NULL,
            nazwa VARCHAR(255) NOT NULL,
            kg FLOAT NOT NULL,
            data_zlecenia DATETIME DEFAULT CURRENT_TIMESTAMP,
            pracownik_id INT NULL,
            potwierdzone BOOLEAN DEFAULT 0,
            potwierdzil_pracownik_id INT NULL,
            data_potwierdzenia DATETIME NULL,
            anulowana BOOLEAN DEFAULT 0,
            data_anulowania DATETIME NULL,
            anulowal_login VARCHAR(100) NULL,
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE CASCADE,
            FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE SET NULL,
            FOREIGN KEY (potwierdzil_pracownik_id) REFERENCES pracownicy(id) ON DELETE SET NULL
        )
    """)

    # Zasyp — pomiar etapów (1-6) dla zlecenia w toku (obsługa PSD + AGRO przez kolumnę linia)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zasyp_etapy (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(10) NOT NULL,
            plan_id INT NOT NULL,
            data_planu DATE NOT NULL,
            etap TINYINT NOT NULL,
            czas_start DATETIME NULL,
            czas_stop DATETIME NULL,
            start_login VARCHAR(100) NULL,
            stop_login VARCHAR(100) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_zasyp_etapy_linia_plan_etap (linia, plan_id, etap),
            INDEX idx_zasyp_etapy_linia_data (linia, data_planu),
            INDEX idx_zasyp_etapy_linia_plan (linia, plan_id)
        )
    """)

    # Zasyp — parametry per zlecenie (np. wielkość szarży do liczenia wydajności)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zasyp_etapy_parametry (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(10) NOT NULL,
            plan_id INT NOT NULL,
            data_planu DATE NOT NULL,
            wielkosc_szarzy_kg FLOAT NULL,
            updated_by_login VARCHAR(100) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_zasyp_etapy_param_linia_plan (linia, plan_id),
            INDEX idx_zasyp_etapy_param_linia_data (linia, data_planu),
            INDEX idx_zasyp_etapy_param_linia_plan (linia, plan_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS powiadomienia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            typ VARCHAR(50) NOT NULL,
            tytul VARCHAR(255) NOT NULL,
            tresc TEXT NOT NULL,
            odbiorca_rola VARCHAR(50) NOT NULL,
            odbiorca_login VARCHAR(100) NULL,
            link_url VARCHAR(255) NULL,
            plan_id INT NULL,
            created_by_user_id INT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_powiadomienia_rola_data (odbiorca_rola, created_at),
            INDEX idx_powiadomienia_login_data (odbiorca_login, created_at),
            INDEX idx_powiadomienia_active (is_active, created_at),
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by_user_id) REFERENCES uzytkownicy(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS powiadomienia_odczyty (
            notification_id INT NOT NULL,
            user_id INT NOT NULL,
            read_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (notification_id, user_id),
            FOREIGN KEY (notification_id) REFERENCES powiadomienia(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES uzytkownicy(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aktywne_sesje (
            session_id VARCHAR(64) PRIMARY KEY,
            user_id INT NOT NULL,
            login VARCHAR(50) NOT NULL,
            rola VARCHAR(20) DEFAULT '',
            pracownik_id INT NULL,
            display_name VARCHAR(100) NULL,
            ip_address VARCHAR(64) NULL,
            last_path VARCHAR(255) NULL,
            logged_in_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            INDEX idx_aktywne_sesje_seen (is_active, last_seen),
            INDEX idx_aktywne_sesje_user (user_id, is_active),
            FOREIGN KEY (user_id) REFERENCES uzytkownicy(id) ON DELETE CASCADE,
            FOREIGN KEY (pracownik_id) REFERENCES pracownicy(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS push_subskrypcje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            login VARCHAR(50) NOT NULL,
            rola VARCHAR(20) NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used DATETIME NULL,
            is_active BOOLEAN DEFAULT 1,
            UNIQUE KEY unique_endpoint (endpoint(512)),
            INDEX idx_push_user (user_id),
            INDEX idx_push_rola (rola),
            FOREIGN KEY (user_id) REFERENCES uzytkownicy(id) ON DELETE CASCADE
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

    # Osobna tabela bufora dla linii AGRO (FK do plan_produkcji_agro)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bufor_agro (
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
            UNIQUE KEY `bufor_agro_uq_data_produkt_kolejka` (data_planu, produkt, kolejka),
            FOREIGN KEY (zasyp_id) REFERENCES plan_produkcji_agro(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produkty_receptury (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa_produktu VARCHAR(100) NOT NULL UNIQUE,
            nr_receptury VARCHAR(64) DEFAULT '',
            typ_produkcji VARCHAR(50) DEFAULT 'worki_zgrzewane_25',
            opakowanie_id INT NULL DEFAULT NULL,
            etykieta_id INT NULL DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

    # MOM — rozliczenie materiałowe per zlecenie AGRO
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mom_rozliczenia (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT NOT NULL,
            nazwa_zlecenia VARCHAR(255) DEFAULT '',
            data_planu DATE NOT NULL,
            produkt VARCHAR(100) NOT NULL,
            tonaz_planowany FLOAT DEFAULT 0,
            tonaz_rzeczywisty FLOAT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'otwarty',
            zamknal_login VARCHAR(100) NULL,
            data_zamkniecia DATETIME NULL,
            uwagi TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mom_pozycje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            mom_id INT NOT NULL,
            surowiec_nazwa VARCHAR(255) NOT NULL,
            przesunieto_kg FLOAT DEFAULT 0,
            zuzycie_kg FLOAT DEFAULT 0,
            roznica_kg FLOAT DEFAULT 0,
            komentarz TEXT,
            FOREIGN KEY (mom_id) REFERENCES mom_rozliczenia(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agro_workowanie_rozliczenie (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_id INT NOT NULL,
            data_planu DATE NOT NULL,
            produkt VARCHAR(100) NOT NULL,
            opakowanie_id INT NULL,
            opakowanie_nazwa VARCHAR(255) NOT NULL,
            stan_przed FLOAT DEFAULT 0,
            wyprodukowano_szt INT DEFAULT 0,
            szt_na_palecie INT DEFAULT 0,
            kg_na_worek FLOAT DEFAULT 20,
            palety_kg_wykonane FLOAT DEFAULT 0,
            zuzyte_worki FLOAT DEFAULT 0,
            stan_po FLOAT DEFAULT 0,
            autor_login VARCHAR(100) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_agro_work_rozl_data (data_planu),
            INDEX idx_agro_work_rozl_plan (plan_id),
            FOREIGN KEY (plan_id) REFERENCES plan_produkcji_agro(id) ON DELETE CASCADE,
            FOREIGN KEY (opakowanie_id) REFERENCES magazyn_opakowania(id) ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zgloszenia_bledow (
            id BIGINT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            login VARCHAR(50) NOT NULL,
            opis TEXT NOT NULL,
            sciezka VARCHAR(255),
            zalaczniki JSON,
            status VARCHAR(30) DEFAULT 'nowy',
            INDEX idx_zgloszenia_login (login),
            INDEX idx_zgloszenia_status (status)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drukarki (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(100) NOT NULL,
            ip VARCHAR(100) NOT NULL,
            lokalizacja VARCHAR(255) DEFAULT '',
            aktywna TINYINT(1) DEFAULT 1
        )
    """)


def _add_column_if_missing(cursor, table, column, definition, description=""):
    """Helper to add column if it doesn't exist."""
    try:
        # Use information_schema instead of SHOW COLUMNS for better reliability
        cursor.execute(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table, column)
        )
        if not cursor.fetchone():
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                if description:
                    print(f"[MIGRATE] {description}")
            except Exception as e:
                print(f"[WARN] Failed to add column {table}.{column}: {e}")
    except Exception as e:
        print(f"[WARN] Error checking column {table}.{column}: {e}")


def _ensure_unique_index(cursor, table, index_name, columns, description=""):
    """Ensure that a UNIQUE index exists with the exact column order provided."""
    try:
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            ORDER BY SEQ_IN_INDEX
            """,
            (table, index_name),
        )
        existing_columns = [row[0] for row in cursor.fetchall() or []]
        desired_columns = list(columns)
        if existing_columns == desired_columns:
            return

        if existing_columns:
            try:
                cursor.execute(f"ALTER TABLE {table} DROP INDEX {index_name}")
            except Exception:
                pass

        cursor.execute(
            f"ALTER TABLE {table} ADD UNIQUE KEY {index_name} ({', '.join(desired_columns)})"
        )
        if description:
            print(f"[MIGRATE] {description}")
    except Exception as e:
        print(f"[WARN] Failed to ensure unique index {table}.{index_name}: {e}")


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
    _add_column_if_missing(cursor, "dosypki", "szarza_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'szarza_id' do dosypek")
    _add_column_if_missing(cursor, "dosypki", "anulowana", "BOOLEAN DEFAULT 0", "Dodawanie kolumny 'anulowana' do dosypek")
    _add_column_if_missing(cursor, "dosypki", "data_anulowania", "DATETIME NULL", "Dodawanie kolumny 'data_anulowania' do dosypek")
    _add_column_if_missing(cursor, "dosypki", "anulowal_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'anulowal_login' do dosypek")
    
    # szarze columns
    _add_column_if_missing(cursor, "szarze", "nr_szarzy", "INT NULL", "Dodawanie kolumny 'nr_szarzy' do szarze")

    # Compatibility layer for new terminology: keep physical table `szarze`, expose `zasypy` view.
    try:
        cursor.execute("""
            CREATE OR REPLACE VIEW zasypy AS
            SELECT
                id,
                plan_id,
                waga,
                data_dodania,
                godzina,
                pracownik_id,
                status,
                uwagi,
                nr_szarzy,
                nr_szarzy AS nr_zasypu
            FROM szarze
        """)
    except Exception:
        pass
    try:
        cursor.execute("""
            CREATE OR REPLACE VIEW zasypy_agro AS
            SELECT
                id,
                plan_id,
                waga,
                data_dodania,
                godzina,
                pracownik_id,
                status,
                uwagi,
                nr_szarzy,
                nr_szarzy AS nr_zasypu
            FROM szarze_agro
        """)
    except Exception:
        pass
    
    # Update typ_zlecenia for known quality orders
    try:
        cursor.execute("UPDATE plan_produkcji SET typ_zlecenia='jakosc' WHERE LOWER(TRIM(produkt)) IN ('dezynfekcja linii','dezynfekcja')")
    except Exception:
        pass

    # Backfill typ_zlecenia='carry_over_ghost' dla ghost Zasypów stworzonych przed wprowadzeniem pola
    try:
        cursor.execute("""
            UPDATE plan_produkcji
            SET typ_zlecenia = 'carry_over_ghost'
            WHERE LOWER(sekcja) = 'zasyp'
              AND status = 'zakonczone'
              AND real_start IS NULL
              AND (nazwa_zlecenia LIKE 'PRZENIESIONE z%' OR nazwa_zlecenia LIKE 'carry-over z%' OR nazwa_zlecenia LIKE 'Carry-over%')
              AND (typ_zlecenia IS NULL OR typ_zlecenia = '')
        """)
    except Exception:
        pass
    
    # plan_produkcji: Link Workowanie to Zasyp (1:1 relationship for exact order tracking)
    _add_column_if_missing(cursor, "plan_produkcji", "zasyp_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'zasyp_id' - FK linkujacy Workowanie z Zasyp 1:1")

    # zasyp_etapy: one row per hall + plan + szarża + etap
    _ensure_unique_index(
        cursor,
        "zasyp_etapy",
        "uq_zasyp_etapy_linia_plan_etap",
        ["linia", "plan_id", "szarza_nr", "etap"],
        "Aktualizacja unikalności zasyp_etapy do (linia, plan_id, szarza_nr, etap)",
    )

    # AGRO etap 3 i 4 są opcjonalnymi krokami dosypki; nie scalać ich z etapem 2.

    # plan_produkcji_agro columns (AGRO hall)
    _add_column_if_missing(cursor, "plan_produkcji_agro", "typ_produkcji", "VARCHAR(20) DEFAULT 'agro'", "Dodawanie kolumny 'typ_produkcji' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "nazwa_zlecenia", "VARCHAR(255) DEFAULT ''", "Dodawanie kolumny 'nazwa_zlecenia' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "typ_zlecenia", "VARCHAR(50) DEFAULT ''", "Dodawanie kolumny 'typ_zlecenia' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "nr_receptury", "VARCHAR(64) DEFAULT ''", "Dodawanie kolumny 'nr_receptury' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "uszkodzone_worki", "INT DEFAULT 0", "Dodawanie kolumny 'uszkodzone_worki' (AGRO)")
    
    # Dodawanie lokalizacji dla wyrobów gotowych
    _add_column_if_missing(cursor, "magazyn_palety", "lokalizacja", "VARCHAR(50) DEFAULT 'MGW01'", "Dodawanie kolumny 'lokalizacja' do magazyn_palety")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "lokalizacja", "VARCHAR(50) DEFAULT 'MGW01'", "Dodawanie kolumny 'lokalizacja' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "wyjasnienie_rozbieznosci", "TEXT", "Dodawanie kolumny 'wyjasnienie_rozbieznosci' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "is_deleted", "BOOLEAN DEFAULT 0", "Dodawanie kolumny 'is_deleted' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "deleted_at", "DATETIME NULL", "Dodawanie kolumny 'deleted_at' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "zasyp_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'zasyp_id' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji", "start_machine_counter", "INT DEFAULT 0", "Dodawanie kolumny 'start_machine_counter' (PSD)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_machine_counter", "INT DEFAULT 0", "Dodawanie kolumny 'start_machine_counter' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "stop_machine_counter", "INT DEFAULT 0", "Dodawanie kolumny 'stop_machine_counter' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji", "start_pallet_counter", "INT DEFAULT 0", "Dodawanie kolumny 'start_pallet_counter' (PSD)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_pallet_counter", "INT DEFAULT 0", "Dodawanie kolumny 'start_pallet_counter' (AGRO)")
    
    # Ensure warehouse unique indexes for accurate pallet tracking
    # Strict rule: one material per location. Conflicting names will overwrite.
    _ensure_unique_index(cursor, "magazyn_surowce", "uq_surowce_lokal", ["lokalizacja"], "Strict unique index (lokalizacja) for PSD raw materials")
    _ensure_unique_index(cursor, "magazyn_agro_surowce", "uq_agro_surowce_lokal", ["lokalizacja"], "Strict unique index (lokalizacja) for AGRO raw materials")
    _ensure_unique_index(cursor, "magazyn_opakowania", "uq_opakowania_lokal", ["lokalizacja"], "Strict unique index (lokalizacja) for PSD packaging")
    _ensure_unique_index(cursor, "magazyn_agro_opakowania", "uq_agro_opakowania_lokal", ["lokalizacja"], "Strict unique index (lokalizacja) for AGRO packaging")

    # Cleanup old (nazwa, lokalizacja) indexes if they exist
    for tbl in ["magazyn_surowce", "magazyn_agro_surowce", "magazyn_opakowania", "magazyn_agro_opakowania"]:
        try:
            cursor.execute(f"ALTER TABLE {tbl} DROP INDEX uq_{tbl.replace('magazyn_','')}_nazwa_lokal")
        except Exception: pass
    
    # palety_workowanie columns
    _add_column_if_missing(cursor, "palety_workowanie", "tara", "FLOAT DEFAULT 0", "Dodawanie kolumny 'tara' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "waga_brutto", "FLOAT DEFAULT 0", "Dodawanie kolumny 'waga_brutto' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "status", "VARCHAR(20) DEFAULT 'do_przyjecia'", "Dodawanie kolumny 'status' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "dodal_login", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'dodal_login' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "data_potwierdzenia", "DATETIME NULL", "Dodawanie kolumny 'data_potwierdzenia' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "czas_potwierdzenia_s", "INT NULL", "Dodawanie kolumny 'czas_potwierdzenia_s' do palet")
    _add_column_if_missing(cursor, "palety_workowanie", "czas_rzeczywistego_potwierdzenia", "TIME NULL", "Dodawanie kolumny 'czas_rzeczywistego_potwierdzenia' do palet")
    # Store confirmed weight separately to avoid overwriting original Workowanie weight
    _add_column_if_missing(cursor, "palety_workowanie", "waga_potwierdzona", "FLOAT NULL", "Dodawanie kolumny 'waga_potwierdzona' do palet")

    # palety_agro columns (AGRO hall)
    _add_column_if_missing(cursor, "palety_agro", "tara", "FLOAT DEFAULT 0", "Dodawanie kolumny 'tara' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "waga_brutto", "FLOAT DEFAULT 0", "Dodawanie kolumny 'waga_brutto' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "status", "VARCHAR(20) DEFAULT 'do_przyjecia'", "Dodawanie kolumny 'status' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "dodal_login", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'dodal_login' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "data_potwierdzenia", "DATETIME NULL", "Dodawanie kolumny 'data_potwierdzenia' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "czas_potwierdzenia_s", "INT NULL", "Dodawanie kolumny 'czas_potwierdzenia_s' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "czas_rzeczywistego_potwierdzenia", "TIME NULL", "Dodawanie kolumny 'czas_rzeczywistego_potwierdzenia' do palet (AGRO)")
    _add_column_if_missing(cursor, "palety_agro", "waga_potwierdzona", "FLOAT NULL", "Dodawanie kolumny 'waga_potwierdzona' do palet (AGRO)")
    
    # Dodanie nr_palety do tabel buforowych
    _add_column_if_missing(cursor, "palety_workowanie", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do palety_workowanie")
    _add_column_if_missing(cursor, "palety_agro", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do palety_agro")

    # aktywne_sesje columns
    _add_column_if_missing(cursor, "aktywne_sesje", "ip_address", "VARCHAR(64) NULL", "Dodawanie kolumny 'ip_address' do aktywne_sesje")

    # magazyn_palety_agro columns
    _add_column_if_missing(cursor, "magazyn_palety", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do magazyn_palety")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "linia", "VARCHAR(20) DEFAULT 'AGRO'", "Dodawanie kolumny 'linia' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "user_login", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'user_login' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "data_potwierdzenia", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'data_potwierdzenia' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'created_at' do magazyn_palety_agro")
    
    # agro_mix_rozliczenie columns
    _add_column_if_missing(cursor, "agro_mix_rozliczenie", "zuzyte_kiedy", "DATETIME NULL", "Dodawanie kolumny 'zuzyte_kiedy' do agro_mix_rozliczenie")
    
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

    # bufor columns
    _add_column_if_missing(cursor, "bufor", "linia", "VARCHAR(10) DEFAULT 'PSD'", "Dodawanie kolumny 'linia' do bufor (rozróżnienie PSD/AGRO)")

    # magazyn ruch columns
    _add_column_if_missing(cursor, "magazyn_ruch", "zbiornik", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'zbiornik' do magazyn_ruch (nr zbiornika przy pobraniu)")
    _add_column_if_missing(cursor, "magazyn_agro_ruch", "zbiornik", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'zbiornik' do magazyn_agro_ruch (nr zbiornika przy pobraniu)")

    # magazyn ruch – referencja do ruchu źródłowego (np. ZWROT → PRODUKCJA)
    _add_column_if_missing(cursor, "magazyn_ruch", "ruch_zrodlowy_id", "INT NULL", "Dodawanie kolumny 'ruch_zrodlowy_id' do magazyn_ruch")
    _add_column_if_missing(cursor, "magazyn_agro_ruch", "ruch_zrodlowy_id", "INT NULL", "Dodawanie kolumny 'ruch_zrodlowy_id' do magazyn_agro_ruch")

    # notifications targeting and bug replies
    _add_column_if_missing(cursor, "powiadomienia", "odbiorca_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'odbiorca_login' do powiadomienia")
    _add_column_if_missing(cursor, "zgloszenia_bledow", "odpowiedz_admina", "TEXT NULL", "Dodawanie kolumny 'odpowiedz_admina' do zgloszenia_bledow")
    _add_column_if_missing(cursor, "zgloszenia_bledow", "odpowiedz_timestamp", "DATETIME NULL", "Dodawanie kolumny 'odpowiedz_timestamp' do zgloszenia_bledow")
    _add_column_if_missing(cursor, "zgloszenia_bledow", "odpowiedz_by_login", "VARCHAR(50) NULL", "Dodawanie kolumny 'odpowiedz_by_login' do zgloszenia_bledow")

    # Traceability and packaging columns for all warehouse tables
    for tbl in ["magazyn_palety", "magazyn_palety_agro", "magazyn_surowce", "magazyn_agro_surowce", "magazyn_opakowania", "magazyn_agro_opakowania", "magazyn_ruch", "magazyn_agro_ruch"]:
        _add_column_if_missing(cursor, tbl, "lokalizacja", "VARCHAR(100) NULL", f"Dodawanie kolumny 'lokalizacja' do {tbl}")
        _add_column_if_missing(cursor, tbl, "nr_partii", "VARCHAR(100) NULL", f"Dodawanie kolumny 'nr_partii' do {tbl}")
        _add_column_if_missing(cursor, tbl, "data_produkcji", "DATE NULL", f"Dodawanie kolumny 'data_produkcji' do {tbl}")
        _add_column_if_missing(cursor, tbl, "data_przydatnosci", "DATE NULL", f"Dodawanie kolumny 'data_przydatnosci' do {tbl}")
        _add_column_if_missing(cursor, tbl, "typ_opakowania", "VARCHAR(50) DEFAULT 'bags'", f"Dodawanie kolumny 'typ_opakowania' do {tbl}")
        _add_column_if_missing(cursor, tbl, "is_blocked", "BOOLEAN DEFAULT 0", f"Dodawanie kolumny 'is_blocked' do {tbl}")
    
    # Inwentaryzacja wpisy packaging type
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_wpisy", "typ_opakowania", "VARCHAR(50) DEFAULT 'brak'", "Dodawanie kolumny 'typ_opakowania' do wpisów inwentaryzacyjnych")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_wpisy", "jednostka", "VARCHAR(10) DEFAULT 'kg'", "Dodawanie kolumny 'jednostka' do wpisów inwentaryzacyjnych")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_sesje", "lokalizacja", "VARCHAR(100) DEFAULT 'Wszystko'", "Dodawanie kolumny 'lokalizacja' do sesji inwentaryzacyjnych")

    # Własna data produkcji dla planów
    _add_column_if_missing(cursor, "plan_produkcji", "data_produkcji", "DATE DEFAULT NULL", "Dodawanie kolumny 'data_produkcji' (PSD)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "data_produkcji", "DATE DEFAULT NULL", "Dodawanie kolumny 'data_produkcji' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "opakowanie_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'opakowanie_id' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "etykieta_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'etykieta_id' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_operator_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'start_checklist_operator_login' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_operator_at", "DATETIME NULL", "Dodawanie kolumny 'start_checklist_operator_at' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_quality_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'start_checklist_quality_login' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_quality_at", "DATETIME NULL", "Dodawanie kolumny 'start_checklist_quality_at' (AGRO)")

    # Rejestr produktów - domyślny worek/folia i etykieta
    _add_column_if_missing(cursor, "produkty_receptury", "opakowanie_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'opakowanie_id' do rejestru produktów")
    _add_column_if_missing(cursor, "produkty_receptury", "etykieta_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'etykieta_id' do rejestru produktów")

    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji_agro WHERE Key_name = 'idx_plan_agro_opakowanie'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji_agro ADD INDEX idx_plan_agro_opakowanie (opakowanie_id)")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_agro_opakowanie: {e}")

    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji_agro WHERE Key_name = 'idx_plan_agro_etykieta'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji_agro ADD INDEX idx_plan_agro_etykieta (etykieta_id)")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_agro_etykieta: {e}")




    # Allow NULL for paleta_id in history
    try:
        cursor.execute("ALTER TABLE palety_historia MODIFY paleta_id INT NULL")
    except Exception:
        pass


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
        print(f"[AUTH] Hashed {migrated} existing user passwords.")
    
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


def refresh_bufor_queue(conn=None, linia='PSD'):
    """Odświeța bufor - dodaje nowe zlecenia z przepisanymi kolejkami (OPTIMIZED)"""
    close_conn = False
    if conn is None:
        conn = get_db_connection()
        close_conn = True
    
    linia = (linia or 'PSD').upper()
    table_plan = get_table_name('plan_produkcji', linia)
    table_palety = get_table_name('palety_workowanie', linia)
    table_bufor = get_table_name('bufor', linia)

    try:
        cursor = conn.cursor()
        today = date.today()
        # Zakres dat używany przy odświeżaniu bufora - stała konfiguracja z app.config
        start_date = today - timedelta(days=BUFOR_LOOKBACK_DAYS)
        end_date = today + timedelta(days=BUFOR_LOOKAHEAD_DAYS)

        # SYNC 1: Synchronizuj Workowanie.tonaz = Zasyp.tonaz_rzeczywisty
        try:
            cursor.execute(f"""
                UPDATE {table_plan} w
                JOIN {table_plan} z ON z.id = w.zasyp_id
                SET w.tonaz = COALESCE(z.tonaz_rzeczywisty, 0)
                WHERE w.sekcja = 'Workowanie' AND z.sekcja = 'Zasyp'
                  AND COALESCE(z.tonaz_rzeczywisty, 0) > 0
                  AND COALESCE(w.tonaz, 0) = 0
                  AND w.data_planu >= %s AND w.data_planu <= %s
            """, (start_date, end_date))
            if cursor.rowcount > 0:
                print(f"[SYNC-{linia}] Workowanie.tonaz synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz failed ({linia}): {e}")

        # SYNC 2: Synchronizuj Workowanie.tonaz_rzeczywisty = sum palet
        try:
            cursor.execute(f"""
                UPDATE {table_plan} w
                SET w.tonaz_rzeczywisty = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    WHERE pw.plan_id = w.id
                )
                WHERE w.sekcja = 'Workowanie' AND w.data_planu >= %s AND w.data_planu <= %s
            """, (start_date, end_date))
            if cursor.rowcount > 0:
                print(f"[SYNC-{linia}] Workowanie.tonaz_rzeczywisty synchronized: {cursor.rowcount} rows")
        except Exception as e:
            print(f"[WARN] Sync Workowanie.tonaz_rzeczywisty failed ({linia}): {e}")

        # 1. Oznacz wpisy z bufora jako 'zamkniete' gdy nie ma aktywnego Workowania
        #    i nic do rozliczenia (tonaz_rzeczywisty - spakowano <= 0).
        cursor.execute(f"""
            UPDATE {table_bufor}
            SET status = 'zamkniete'
            WHERE status = 'aktywny'
              AND NOT EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja = 'Workowanie' AND w.status IN ('w toku', 'zaplanowane')
                    AND w.produkt = {table_bufor}.produkt AND w.data_planu = {table_bufor}.data_planu
              )
              AND COALESCE({table_bufor}.tonaz_rzeczywisty, 0) - COALESCE({table_bufor}.spakowano, 0) <= 0
        """)
        updated = cursor.rowcount

        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.status = 'zamkniete'
            WHERE b.status = 'aktywny'
              AND z.sekcja = 'Zasyp'
              AND z.real_start IS NULL
              AND z.typ_zlecenia != 'carry_over_ghost'
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Zamknięto {cursor.rowcount} wpisów bufora z Zasypem bez real_start")

        # 1d. Re-otwórz wpisy bufora dla ghost Zasypów (carry-over/przeniesione), które zostały
        #     błędnie zamknięte, gdy Workowanie jest nadal zaplanowane.
        #     Ghost Zasyp ma teraz status='zaplanowane' (nie 'zakonczone'), sprawdzamy przez typ_zlecenia.
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.status = 'aktywny'
            WHERE b.status = 'zamkniete'
              AND z.sekcja = 'Zasyp'
              AND z.typ_zlecenia = 'carry_over_ghost'
              AND EXISTS (
                  SELECT 1 FROM {table_plan} w
                  WHERE w.sekcja = 'Workowanie' AND w.status IN ('w toku', 'zaplanowane')
                    AND w.produkt = b.produkt AND w.data_planu = b.data_planu
              )
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Re-otwarto {cursor.rowcount} wpisów bufora dla ghost Zasypów (carry-over)")

        # 1c. Zamknij osierocone wpisy bufora (zasyp_id wskazuje na nieistniejący plan).
        cursor.execute(f"""
            UPDATE {table_bufor} b
            SET b.status = 'zamkniete'
            WHERE b.status = 'aktywny'
              AND NOT EXISTS (
                  SELECT 1 FROM {table_plan} z WHERE z.id = b.zasyp_id
              )
        """)
        if cursor.rowcount > 0:
            print(f"[CLEANUP-{linia}] Zamknięto {cursor.rowcount} wpisów bufora z Zasypem bez real_start")

        # 2. Pobierz Zasypy dla skonfigurowanego zakresu dat.
        #    ZASADA: do bufora trafia zasyp dopiero gdy pojawi się na zasypie (real_start IS NOT NULL).
        #    Statusy 'w toku' i 'zakonczone' oznaczają, że zasyp faktycznie wystartował.
        #    Zasypy 'zaplanowane' (bez real_start) NIE trafiają do bufora — kolejkowanie
        #    zaczyna się dopiero gdy zlecenie pojawi się fizycznie na zasypie.
        cursor.execute(f"""
            SELECT z.id, z.data_planu, z.produkt, z.nazwa_zlecenia, z.typ_produkcji,
                   COALESCE(NULLIF(z.tonaz_rzeczywisty, 0), z.tonaz) AS efektywny_tonaz,
                   z.status
            FROM {table_plan} z
            INNER JOIN {table_plan} w ON w.zasyp_id = z.id
            WHERE z.sekcja = 'Zasyp' AND w.sekcja = 'Workowanie'
              AND w.status IN ('w toku', 'zaplanowane')
              AND (
                  -- Normalne Zasypy: muszą mieć real_start i status 'w toku' lub 'zakonczone'
                  (z.status IN ('w toku', 'zakonczone') AND z.real_start IS NOT NULL)
                  OR
                  -- Ghost Zasypy (carry-over): zaplanowane, brak real_start, ale mają tonaz w zleceniu Workowanie
                  (z.typ_zlecenia = 'carry_over_ghost' AND z.status = 'zaplanowane')
              )
              AND z.data_planu >= %s AND z.data_planu <= %s
              AND COALESCE(NULLIF(w.tonaz, 0), 0) > 0
            ORDER BY z.data_planu DESC, COALESCE(z.real_start, '00:00:00') ASC, z.id ASC
        """, (start_date, end_date))

        zasypy_do_bufora = cursor.fetchall()

        # 3. Dodaj brakujące Zasypy do bufora
        added = 0
        for z_id, z_data, z_produkt, z_nazwa, z_typ, z_tonaz, z_status in zasypy_do_bufora:
            cursor.execute(
                f"SELECT id FROM {table_bufor} WHERE zasyp_id = %s AND status = 'aktywny'",
                (z_id,)
            )
            if cursor.fetchone():
                continue

            # Pobierz max kolejkę (po WSZYSTKICH statusach — unique key jest globalna) i ilość spakowanego
            cursor.execute(f"""
                SELECT COALESCE(MAX(b.kolejka), 0), COALESCE(SUM(pw.waga), 0)
                FROM {table_bufor} b
                LEFT JOIN {table_palety} pw ON pw.plan_id IN (
                    SELECT id FROM {table_plan}
                    WHERE data_planu = %s AND produkt = %s AND sekcja = 'Workowanie'
                )
                WHERE b.data_planu = %s AND b.produkt = %s
            """, (z_data, z_produkt, z_data, z_produkt))

            result = cursor.fetchone()
            next_kolejka = (result[0] or 0) + 1
            spakowano = result[1] or 0

            # Sprawdź, czy dla tej daty/produktu/kolejki już istnieje wpis (dowolny status)
            cursor.execute(
                f"SELECT id FROM {table_bufor} WHERE data_planu = %s AND produkt = %s AND kolejka = %s",
                (z_data, z_produkt, next_kolejka)
            )
            if cursor.fetchone():
                continue

            # Dodaj do bufora
            cursor.execute(f"""
                INSERT INTO {table_bufor}
                (zasyp_id, data_planu, produkt, nazwa_zlecenia, typ_produkcji,
                 tonaz_rzeczywisty, spakowano, kolejka, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'aktywny')
            """, (z_id, z_data, z_produkt, z_nazwa or '', z_typ or 'worki_zgrzewane_25',
                  z_tonaz, spakowano, next_kolejka))
            if cursor.rowcount:
                added += 1

        # 4. Renumeruj kolejki (dwustopniowo — unikamy konfliktu z wpisami 'zamkniete')
        #
        # Problem: ROW_NUMBER zaczyna od 1, ale wpisy 'zamkniete' mogą zajmować niskie numery
        # dla tego samego (data_planu, produkt). Bezpośrednia UPDATE-a powoduje Duplicate Key.
        #
        # Rozwiązanie:
        #   Krok 4a — przesuń wszystkie aktywne do strefy tymczasowej (ujemne -id, gwarantowanie unikalne).
        #   Krok 4b — przypisz właściwe numery startujące od MAX(zamkniete)+1 (globalnie na datę),
        #             posortowane wg real_start zasypu (CASE WHEN, bo MySQL NULL < wartości w ASC).

        cursor.execute(f"""
            UPDATE {table_bufor}
            SET kolejka = -id
            WHERE status = 'aktywny'
              AND data_planu >= %s AND data_planu <= %s
        """, (start_date, end_date))

        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN (
                SELECT b2.id,
                       (SELECT COALESCE(MAX(b3.kolejka), 0)
                        FROM {table_bufor} b3
                        WHERE b3.data_planu = b2.data_planu
                          AND b3.status != 'aktywny')
                       + ROW_NUMBER() OVER (
                           PARTITION BY b2.data_planu
                           ORDER BY b2.data_planu DESC,
                                    CASE WHEN (SELECT z.real_start FROM {table_plan} z WHERE z.id = b2.zasyp_id) IS NOT NULL THEN 0 ELSE 1 END ASC,
                                    COALESCE((SELECT z.real_start FROM {table_plan} z WHERE z.id = b2.zasyp_id), '9999-12-31 23:59:59') ASC,
                                    b2.id ASC
                       ) AS nowa_kolejka
                FROM {table_bufor} b2
                WHERE b2.status = 'aktywny'
            ) ranked ON b.id = ranked.id
            SET b.kolejka = ranked.nowa_kolejka
        """)

        # 5. Aktualizuj tonaz_rzeczywisty i spakowano w jednym UPDATE
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            SET b.tonaz_rzeczywisty = COALESCE(z.tonaz_rzeczywisty, 0),
                b.spakowano = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    INNER JOIN {table_plan} w ON pw.plan_id = w.id
                    WHERE w.data_planu = b.data_planu AND w.produkt = b.produkt
                      AND w.sekcja = 'Workowanie'
                )
            WHERE b.status = 'aktywny'
              AND COALESCE(z.tonaz_rzeczywisty, 0) > 0
              AND COALESCE(z.typ_zlecenia, '') != 'carry_over_ghost'
        """)

        # 5b. Dla ghost Zasypów (carry_over_ghost): tonaz_rzeczywisty bufora bierzemy z Workowanie.tonaz
        #     bo Zasyp ghost ma tonaz_rzeczywisty=0 (nie był fizycznie sypany)
        cursor.execute(f"""
            UPDATE {table_bufor} b
            JOIN {table_plan} z ON z.id = b.zasyp_id
            JOIN {table_plan} w ON w.zasyp_id = z.id AND w.sekcja = 'Workowanie'
            SET b.tonaz_rzeczywisty = COALESCE(w.tonaz, 0),
                b.spakowano = (
                    SELECT COALESCE(SUM(pw.waga), 0) FROM {table_palety} pw
                    WHERE pw.plan_id = w.id
                )
            WHERE b.status = 'aktywny'
              AND z.typ_zlecenia = 'carry_over_ghost'
              AND z.sekcja = 'Zasyp'
              AND COALESCE(w.tonaz, 0) > 0
        """)

        conn.commit()
        print(f"[BUFOR-{linia}] Refreshed buffer: marked_closed {updated}, added {added}")
        
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


def _table_has_column(cursor, table_name, column_name):
    try:
        cursor.execute(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table_name, column_name),
        )
        return bool(cursor.fetchone())
    except Exception:
        return False


def _standardize_warehouse_pallet_ids(cursor):
    """Normalize all warehouse nr_palety values to SSCC-like format: AAA + 18 digits."""
    from app.utils.pallet_id import generate_pallet_id, is_valid_pallet_id

    table_specs = [
        {'table': 'magazyn_surowce', 'type': 'surowiec', 'linia': 'PSD'},
        {'table': 'magazyn_opakowania', 'type': 'opakowanie', 'linia': 'PSD'},
        {'table': 'magazyn_dodatki', 'type': 'dodatek', 'linia': 'PSD'},
        {'table': 'magazyn_palety', 'type': 'wyrób gotowy', 'linia': 'PSD'},
        {'table': 'magazyn_palety_agro', 'type': 'wyrób gotowy', 'linia': 'AGRO'},
        {'table': 'palety_workowanie', 'type': 'wyrób gotowy', 'linia': 'PSD'},
        {'table': 'palety_agro', 'type': 'wyrób gotowy', 'linia': 'AGRO'},
    ]

    total_updated = 0
    for spec in table_specs:
        table_name = spec['table']

        if not _table_has_column(cursor, table_name, 'id'):
            continue
        if not _table_has_column(cursor, table_name, 'nr_palety'):
            continue

        try:
            cursor.execute(
                f"SELECT id, nr_palety FROM {table_name} "
                "WHERE nr_palety IS NULL OR TRIM(nr_palety) = '' OR nr_palety NOT REGEXP '^[A-Za-z]{3}[0-9]{18}$'"
            )
        except Exception:
            continue

        rows = cursor.fetchall() or []
        updated = 0
        for row_id, old_nr_palety in rows:
            if is_valid_pallet_id(old_nr_palety):
                continue

            new_nr_palety = generate_pallet_id(spec['linia'], type=spec['type'], record_id=row_id)
            cursor.execute(
                f"UPDATE {table_name} SET nr_palety = %s WHERE id = %s",
                (new_nr_palety, row_id),
            )
            updated += 1

        if updated:
            total_updated += updated
            print(f"[MIGRATE] Standaryzacja SSCC w {table_name}: {updated} rekordow")

    if total_updated:
        print(f"[OK] Zaktualizowano {total_updated} rekordow nr_palety do formatu AAA+18 cyfr")


def _seed_produkty(cursor):
    """Seed initial products/recipes into produkty_receptury table."""
    default_products = [
        ('MOM INSTANT', '', 'worki_zgrzewane_25'),
        ('MILK BAND BIAŁE', '', 'worki_zgrzewane_25'),
        ('HOLENDER', '', 'worki_zgrzewane_25'),
        ('testowe 45', '', 'worki_zgrzewane_25'),
    ]
    
    for nazwa, nr_receptury, typ in default_products:
        cursor.execute(
            "SELECT id FROM produkty_receptury WHERE nazwa_produktu=%s",
            (nazwa,)
        )
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO produkty_receptury (nazwa_produktu, nr_receptury, typ_produkcji) VALUES (%s, %s, %s)",
                (nazwa, nr_receptury, typ)
            )
    
    print("[OK] Produkty zainicjalizowane w bazie danych")


def _seed_etykiety(cursor):
    """Seed initial labels into slownik_etykiety_agro table."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS slownik_etykiety_agro (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(255) UNIQUE NOT NULL
        )
    """)
    
    default_labels = [
        "Biała",
        "Biała z paskiem brązowym",
        "Biała z paskiem czerwonym",
        "Biała z paskiem fioletowym",
        "Biała z paskiem żółtym"
    ]
    for label in default_labels:
        cursor.execute("SELECT id FROM slownik_etykiety_agro WHERE nazwa=%s", (label,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO slownik_etykiety_agro (nazwa) VALUES (%s)", (label,))
    
    print("[OK] Etykiety AGRO zainicjalizowane w bazie danych")


def setup_database():
    """Main setup function - orchestrates all database initialization."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Create all base tables
        _create_tables(cursor)
        
        # 2. Run migrations (add missing columns)
        _migrate_columns(cursor)

        # 2b. Normalize existing pallet IDs to SSCC-like format (AAA + 18 digits)
        _standardize_warehouse_pallet_ids(cursor)
        
        # 3. Seed initial products
        _seed_produkty(cursor)
        
        # Seed labels
        _seed_etykiety(cursor)
        
        # 4. Seed default users (including password migration)
        _seed_default_users(cursor)
        
        # 5. Auto-confirm all palety with data_dodania and set confirmation time to +2 min
        # NOTE: This migration could auto-confirm recently added palety on every app
        # startup. Only run it when explicitly requested via environment variable
        # `AUTO_CONFIRM_PALET=1` to avoid unexpected automatic acceptance.
        if os.environ.get('AUTO_CONFIRM_PALET') == '1':
            _auto_confirm_existing_palety(cursor)
        else:
            print("[INFO] Skipping auto-confirm palet on startup (AUTO_CONFIRM_PALET not set)")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("[OK] Baza danych jest gotowa!")
        
        # 6. Odświeź bufor dla obu linii
        refresh_bufor_queue(linia='PSD')
        refresh_bufor_queue(linia='AGRO')
        
    except Exception as e:
        print(f"[ERROR] Blad podczas inicjalizacji bazy danych: {e}")
        raise


def rollover_unfinished(from_date, to_date):
    """Przenosi niezakończone zlecenia z `from_date` na `to_date`.
    Zlecenia przenoszone są jako nowe wiersze z datą docelową, statusem
    'zaplanowane' (reset real_start/real_stop) i odpowiednią kolejnością.
            # Ensure a uniqueness constraint to prevent multiple Workowanie rows pointing to the same zasyp_id
            try:
                cursor.execute("SHOW INDEX FROM plan_produkcji WHERE Key_name = 'uq_plan_produkcji_zasyp_sekcja'")
                if not cursor.fetchone():
                    try:
                        cursor.execute("ALTER TABLE plan_produkcji ADD UNIQUE INDEX uq_plan_produkcji_zasyp_sekcja (zasyp_id, sekcja)")
                    except Exception:
                        # If index creation fails (e.g., existing conflicting data), skip — migration scripts handle deduplication separately
                        pass
            except Exception:
                pass
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


def insert_dosypka(plan_id, nazwa, kg, pracownik_id=None):
    """Insert single dosypka record."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dosypki (plan_id, nazwa, kg, pracownik_id, potwierdzone) VALUES (%s, %s, %s, %s, 0)",
            (plan_id, nazwa, kg, pracownik_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def list_unconfirmed_dosypki(linia='PSD'):
    """Return list of active unconfirmed dosypki."""
    try:
        table_dosypki = get_table_name('dosypki', linia)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, plan_id, nazwa, kg, data_zlecenia, pracownik_id,
                   COALESCE(anulowana, 0), anulowal_login, data_anulowania
            FROM {table_dosypki}
            WHERE potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
            ORDER BY data_zlecenia ASC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []


def confirm_dosypka(dosypka_id, potwierdzil_pracownik_id=None, linia='PSD'):
    """Mark dosypka as confirmed (odczytanie) and sync plan's tonaz_rzeczywisty."""
    try:
        table_dosypki = get_table_name('dosypki', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        table_szarze = get_table_name('szarze', linia)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get plan_id first
        cursor.execute(f"SELECT plan_id FROM {table_dosypki} WHERE id=%s", (dosypka_id,))
        row = cursor.fetchone()
        plan_id = row[0] if row else None
        
        # Update dosypka status
        cursor.execute(f"UPDATE {table_dosypki} SET potwierdzone=1, potwierdzil_pracownik_id=%s, data_potwierdzenia=NOW() WHERE id=%s", (potwierdzil_pracownik_id, dosypka_id))
        
        # Synchronize plan's tonaz_rzeczywisty = SUM(szarże) + SUM(dosypki potwierdzone)
        if plan_id:
            cursor.execute(
                f"UPDATE {table_plan} SET tonaz_rzeczywisty = "
                f"COALESCE((SELECT SUM(waga) FROM {table_szarze} WHERE plan_id = %s), 0) + "
                f"COALESCE((SELECT SUM(kg) FROM {table_dosypki} WHERE plan_id = %s AND potwierdzone = 1 AND COALESCE(anulowana, 0) = 0), 0) "
                f"WHERE id = %s",
                (plan_id, plan_id, plan_id)
            )
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def get_plan_notification_context(plan_id, conn=None, cursor=None, linia='PSD'):
    """Return minimal plan context used to build notification content."""
    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    try:
        table_plan = get_table_name('plan_produkcji', linia)
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor(dictionary=True)
        local_cursor.execute(
            f"""
            SELECT id, produkt, sekcja, data_planu, COALESCE(typ_produkcji, '') AS typ_produkcji,
                   COALESCE(nazwa_zlecenia, '') AS nazwa_zlecenia
            FROM {table_plan}
            WHERE id = %s
            """,
            (plan_id,)
        )
        return local_cursor.fetchone()
    except Exception:
        return None
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def create_notifications(typ, tytul, tresc, recipient_roles, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Create one notification row for each recipient role."""
    if not recipient_roles:
        return []

    if isinstance(recipient_roles, str):
        recipient_roles = [recipient_roles]

    normalized_roles = []
    for role in recipient_roles:
        role_value = str(role or '').strip().lower()
        if role_value and role_value not in normalized_roles:
            normalized_roles.append(role_value)

    if not normalized_roles:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    created_ids = []

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        for role in normalized_roles:
            local_cursor.execute(
                """
                INSERT INTO powiadomienia
                    (typ, tytul, tresc, odbiorca_rola, odbiorca_login, link_url, plan_id, created_by_user_id)
                VALUES (%s, %s, %s, %s, NULL, %s, %s, %s)
                """,
                (typ, tytul, tresc, role, link_url, plan_id, created_by_user_id)
            )
            try:
                created_ids.append(local_cursor.lastrowid)
            except Exception:
                pass

        if own_conn:
            local_conn.commit()

        # Wyślij Web Push do subskrybowanych urządzeń dla każdej roli (w tle, nieblokująco)
        try:
            from app.services.push_service import send_push_to_roles
            _push_url = link_url or '/'
            import threading
            threading.Thread(
                target=send_push_to_roles,
                args=(normalized_roles, tytul, tresc, _push_url),
                daemon=True
            ).start()
        except Exception:
            pass  # Push jest opcjonalny — błąd nie blokuje zapisu powiadomień

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def create_notification_for_login(typ, tytul, tresc, recipient_login, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Create a notification targeted to a single user login."""
    login_value = str(recipient_login or '').strip()
    if not login_value:
        return None

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        local_cursor.execute(
            """
            INSERT INTO powiadomienia
                (typ, tytul, tresc, odbiorca_rola, odbiorca_login, link_url, plan_id, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (typ, tytul, tresc, '__login__', login_value, link_url, plan_id, created_by_user_id),
        )

        inserted_id = None
        try:
            inserted_id = local_cursor.lastrowid
        except Exception:
            inserted_id = None

        if own_conn:
            local_conn.commit()

        # Wyślij Web Push do urządzeń konkretnego użytkownika (w tle)
        try:
            from app.services.push_service import send_push_to_login
            _push_url = link_url or '/'
            import threading
            threading.Thread(
                target=send_push_to_login,
                args=(login_value, tytul, tresc, _push_url),
                daemon=True
            ).start()
        except Exception:
            pass  # Push jest opcjonalny

        return inserted_id
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def list_unread_notifications(user_id, role, login=None, limit=20, linia='PSD'):
    """Return unread notifications for a single user and role."""
    if not user_id or not role:
        return []

    safe_limit = max(1, min(int(limit or 20), 100))
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT p.id, p.typ, p.tytul, p.tresc, p.link_url, p.plan_id, p.created_at, p.odbiorca_rola
            FROM powiadomienia p
            LEFT JOIN powiadomienia_odczyty po
                ON po.notification_id = p.id AND po.user_id = %s
            WHERE p.is_active = 1
              AND (
                    p.odbiorca_rola = %s
                    OR (p.odbiorca_login IS NOT NULL AND LOWER(p.odbiorca_login) = LOWER(%s))
                  )
              AND po.notification_id IS NULL
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT %s
            """,
            (user_id, str(role).strip().lower(), str(login or '').strip(), safe_limit)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []


def mark_notification_read(notification_id, user_id, role=None, login=None, linia='PSD'):
    """Mark a single notification as read for the given user."""
    if not notification_id or not user_id:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM powiadomienia
            WHERE id = %s
              AND is_active = 1
              AND (
                    odbiorca_rola = %s
                    OR (odbiorca_login IS NOT NULL AND LOWER(odbiorca_login) = LOWER(%s))
                  )
            LIMIT 1
            """,
            (notification_id, str(role or '').strip().lower(), str(login or '').strip()),
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return False

        cursor.execute(
            """
            INSERT IGNORE INTO powiadomienia_odczyty (notification_id, user_id)
            VALUES (%s, %s)
            """,
            (notification_id, user_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def mark_all_notifications_read(user_id, role, login=None, linia='PSD'):
    """Mark all unread notifications for a role as read for the given user."""
    if not user_id or not role:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT IGNORE INTO powiadomienia_odczyty (notification_id, user_id)
            SELECT p.id, %s
            FROM powiadomienia p
            LEFT JOIN powiadomienia_odczyty po
                ON po.notification_id = p.id AND po.user_id = %s
            WHERE p.is_active = 1
              AND (
                    p.odbiorca_rola = %s
                    OR (p.odbiorca_login IS NOT NULL AND LOWER(p.odbiorca_login) = LOWER(%s))
                  )
              AND po.notification_id IS NULL
            """,
            (user_id, user_id, str(role).strip().lower(), str(login or '').strip())
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def replace_active_notifications(typ, recipient_roles, tytul, tresc, link_url=None, plan_id=None, created_by_user_id=None, conn=None, cursor=None):
    """Replace active notifications of a given type/plan for the provided roles."""
    if not recipient_roles:
        return []

    if isinstance(recipient_roles, str):
        recipient_roles = [recipient_roles]

    normalized_roles = []
    for role in recipient_roles:
        role_value = str(role or '').strip().lower()
        if role_value and role_value not in normalized_roles:
            normalized_roles.append(role_value)

    if not normalized_roles:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        placeholders = ','.join(['%s'] * len(normalized_roles))
        query = (
            "UPDATE powiadomienia SET is_active = 0 "
            "WHERE is_active = 1 AND typ = %s AND odbiorca_rola IN (" + placeholders + ")"
        )
        params = [typ] + normalized_roles
        if plan_id is None:
            query += " AND plan_id IS NULL"
        else:
            query += " AND plan_id = %s"
            params.append(plan_id)

        local_cursor.execute(query, tuple(params))
        created_ids = create_notifications(
            typ=typ,
            tytul=tytul,
            tresc=tresc,
            recipient_roles=normalized_roles,
            link_url=link_url,
            plan_id=plan_id,
            created_by_user_id=created_by_user_id,
            conn=local_conn,
            cursor=local_cursor,
        )

        if own_conn:
            local_conn.commit()

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def deactivate_notifications(typ, recipient_roles=None, plan_id=None, conn=None, cursor=None):
    """Deactivate active notifications matching provided filters."""
    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor()

        query = "UPDATE powiadomienia SET is_active = 0 WHERE is_active = 1 AND typ = %s"
        params = [typ]

        if recipient_roles:
            if isinstance(recipient_roles, str):
                recipient_roles = [recipient_roles]
            normalized_roles = [str(role or '').strip().lower() for role in recipient_roles if str(role or '').strip()]
            if normalized_roles:
                placeholders = ','.join(['%s'] * len(normalized_roles))
                query += " AND odbiorca_rola IN (" + placeholders + ")"
                params.extend(normalized_roles)

        if plan_id is None:
            query += " AND plan_id IS NULL"
        else:
            query += " AND plan_id = %s"
            params.append(plan_id)

        local_cursor.execute(query, tuple(params))
        if own_conn:
            local_conn.commit()
        return True
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return False
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def sync_dosypka_notifications(plan_id, author_name=None, created_by_user_id=None, conn=None, cursor=None, linia='PSD'):
    """Keep dosypka notifications aligned with current unconfirmed rows for a plan."""
    if not plan_id:
        return []

    own_conn = conn is None
    own_cursor = cursor is None
    local_conn = conn
    local_cursor = cursor
    recipient_roles = ('operator', 'pracownik', 'produkcja', 'lider', 'laborant', 'admin', 'zarzad', 'masteradmin')

    table_plan = get_table_name('plan_produkcji', linia)
    table_dosypki = get_table_name('dosypki', linia)

    try:
        if own_conn:
            local_conn = get_db_connection()
        if own_cursor:
            local_cursor = local_conn.cursor(dictionary=True)

        local_cursor.execute(
            f"""
            SELECT id, produkt, data_planu
            FROM {table_plan}
            WHERE id = %s
            """,
            (plan_id,)
        )
        plan_context = local_cursor.fetchone()
        if not plan_context:
            deactivate_notifications('dosypka', recipient_roles=recipient_roles, plan_id=plan_id, conn=local_conn, cursor=local_cursor)
            if own_conn:
                local_conn.commit()
            return []

        local_cursor.execute(
            f"""
            SELECT nazwa, kg
            FROM {table_dosypki}
            WHERE plan_id = %s AND potwierdzone = 0 AND COALESCE(anulowana, 0) = 0
            ORDER BY data_zlecenia ASC, id ASC
            """,
            (plan_id,)
        )
        pending_rows = local_cursor.fetchall()

        if not pending_rows:
            deactivate_notifications('dosypka', recipient_roles=recipient_roles, plan_id=plan_id, conn=local_conn, cursor=local_cursor)
            if own_conn:
                local_conn.commit()
            return []

        # ... (rest of function unchanged, but using table-specific data)
        produkt = plan_context.get('produkt') or 'Zasyp'
        data_planu = plan_context.get('data_planu')
        author_display = str(author_name or '').strip() or 'Użytkownik'
        total_kg = sum(float(row.get('kg') or 0) for row in pending_rows)
        pending_count = len(pending_rows)
        only_no_dosypka = pending_count == 1 and str((pending_rows[0].get('nazwa') or '')).strip().lower() == 'brak dosypki'

        if only_no_dosypka:
            tytul = f'Brak dosypki: {produkt}'
            tresc = f'{author_display} oznaczył brak dosypki dla {produkt}.'
        elif pending_count == 1:
            tytul = f'Nowa dosypka: {produkt}'
            tresc = f'{author_display} dodał dosypkę {total_kg:.1f} kg dla {produkt}.'
        else:
            tytul = f'Dosypki oczekujące: {produkt}'
            tresc = f'{author_display} dodał {pending_count} pozycji dosypki, razem {total_kg:.1f} kg, dla {produkt}.'

        link_url = f'/?sekcja=Zasyp&data={data_planu}&linia={linia}' if data_planu else f'/?sekcja=Zasyp&linia={linia}'
        created_ids = replace_active_notifications(
            typ='dosypka',
            recipient_roles=recipient_roles,
            tytul=tytul,
            tresc=tresc,
            link_url=link_url,
            plan_id=plan_id,
            created_by_user_id=created_by_user_id,
            conn=local_conn,
            cursor=local_cursor,
        )

        if own_conn:
            local_conn.commit()

        return created_ids
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
        return []
    finally:
        if own_cursor and local_cursor:
            try:
                local_cursor.close()
            except Exception:
                pass
        if own_conn and local_conn:
            try:
                local_conn.close()
            except Exception:
                pass


def ensure_session_tracking_id(current_session_id=None):
    """Return a stable session tracking id."""
    value = str(current_session_id or '').strip()
    if value:
        return value
    return uuid.uuid4().hex


def touch_active_session(session_id, user_id, login, role, pracownik_id=None, display_name=None, last_path=None, ip_address=None, conn=None):
    """Upsert active session heartbeat for online users view."""
    if not session_id or not user_id or not login:
        return False

    own_conn = False
    local_conn = conn
    cursor = None
    try:
        if local_conn is None:
            local_conn = get_db_connection()
            own_conn = True
        cursor = local_conn.cursor()
        cursor.execute(
            """
            INSERT INTO aktywne_sesje (
                session_id, user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), 1)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                login = VALUES(login),
                rola = VALUES(rola),
                pracownik_id = VALUES(pracownik_id),
                display_name = VALUES(display_name),
                ip_address = VALUES(ip_address),
                last_path = VALUES(last_path),
                last_seen = NOW(),
                is_active = 1
            """,
            (session_id, user_id, login, str(role or '').lower(), pracownik_id, display_name, ip_address, last_path)
        )
        if own_conn:
            local_conn.commit()
        cursor.close()
        if own_conn:
            local_conn.close()
        return True
    except Exception:
        if own_conn and local_conn:
            try:
                local_conn.rollback()
            except Exception:
                pass
            try:
                local_conn.close()
            except Exception:
                pass
        return False


def deactivate_active_session(session_id):
    """Mark a session as logged out."""
    if not session_id:
        return False

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE session_id = %s",
            (session_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def list_online_users(active_within_minutes=30):
    """Return recent or active sessions for online users view."""
    minutes = max(1, min(int(active_within_minutes or 30), 240))
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT session_id, user_id, login, rola, pracownik_id, display_name, last_path, logged_in_at, last_seen,
                     ip_address, is_active,
                   TIMESTAMPDIFF(SECOND, last_seen, NOW()) AS idle_seconds
            FROM aktywne_sesje
            WHERE last_seen >= DATE_SUB(NOW(), INTERVAL %s MINUTE)
            ORDER BY is_active DESC, last_seen DESC, login ASC
            """,
            (minutes,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return []


def deactivate_all_user_sessions(user_id):
    """Mark all active sessions of a user as logged out in the database."""
    if not user_id:
        return False
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE aktywne_sesje SET is_active = 0, last_seen = NOW() WHERE user_id = %s",
            (user_id,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        return False


def is_session_active(session_id):
    """Check if the session tracking ID is still active in the database."""
    if not session_id:
        return False
    
    from flask import session, request
    from datetime import datetime
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT is_active FROM aktywne_sesje WHERE session_id = %s",
            (session_id,)
        )
        row = cursor.fetchone()
        
        # If the session exists in DB, respect its active status
        if row is not None:
            is_act = row[0]
            cursor.close()
            conn.close()
            return is_act == 1
            
        # If the session does NOT exist in DB, but the Flask session cookie claims
        # we are logged in, we automatically replicate/reconstruct the session context!
        # This prevents database switches or purges from logging the user out.
        if session.get('zalogowany') and session.get('user_id'):
            u_id = session.get('user_id')
            u_login = session.get('login')
            u_rola = session.get('rola') or ''
            u_prac = session.get('pracownik_id')
            u_name = session.get('imie_nazwisko') or u_login
            u_grupa = session.get('grupa')
            
            # 1. Ensure the employee exists
            if u_prac:
                cursor.execute("SELECT id FROM pracownicy WHERE id = %s", (u_prac,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO pracownicy (id, imie_nazwisko) VALUES (%s, %s)",
                        (u_prac, u_name)
                    )
            
            # 2. Ensure the user exists
            cursor.execute("SELECT id FROM uzytkownicy WHERE id = %s", (u_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO uzytkownicy (id, login, haslo, rola, pracownik_id, grupa) VALUES (%s, %s, %s, %s, %s, %s)",
                    (u_id, u_login, 'replicated_dummy_hash', u_rola, u_prac, u_grupa)
                )
                
            # 3. Create the active session
            forwarded_for = request.headers.get('X-Forwarded-For', '')
            client_ip = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr)
            cursor.execute("""
                INSERT INTO aktywne_sesje 
                (session_id, user_id, login, rola, pracownik_id, display_name, ip_address, last_path, logged_in_at, last_seen, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, (
                session_id,
                u_id,
                u_login,
                u_rola,
                u_prac,
                u_name,
                client_ip,
                request.path,
                datetime.now(),
                datetime.now()
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
            
        cursor.close()
        conn.close()
        return False
    except Exception as e:
        print(f"[WARN] Failed auto-replicating session context in is_session_active: {e}")
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return True  # Fallback to True on DB error to prevent blocking users


# ===========================================================================
# WEB PUSH SUBSCRIPTION HELPERS
# ===========================================================================

def save_push_subscription(user_id: int, login: str, rola: str, endpoint: str, p256dh: str, auth: str) -> bool:
    """Zapisz lub zaktualizuj subskrypcję Web Push dla użytkownika.

    Args:
        user_id: ID użytkownika
        login: Login użytkownika
        rola: Rola użytkownika
        endpoint: URL endpointu push (unikalny per urządzenie)
        p256dh: Klucz publiczny szyfrowania (base64)
        auth: Sekret autoryzacji (base64)

    Returns:
        True jeśli operacja się powiodła
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO push_subskrypcje (user_id, login, rola, endpoint, p256dh, auth, last_used, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), 1)
            ON DUPLICATE KEY UPDATE
                user_id = VALUES(user_id),
                login   = VALUES(login),
                rola    = VALUES(rola),
                p256dh  = VALUES(p256dh),
                auth    = VALUES(auth),
                last_used = NOW(),
                is_active = 1
            """,
            (user_id, login, rola, endpoint, p256dh, auth)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] save_push_subscription error: %s", e)
        return False


def delete_push_subscription(endpoint: str) -> bool:
    """Usuń subskrypcję push po jej endpointcie (np. gdy urządzenie ją odwołało).

    Args:
        endpoint: URL endpointu push do usunięcia

    Returns:
        True jeśli usunięto
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM push_subskrypcje WHERE endpoint = %s", (endpoint,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] delete_push_subscription error: %s", e)
        return False


def get_push_subscriptions_for_role(rola: str) -> list:
    """Pobierz aktywne subskrypcje push dla danej roli.

    Args:
        rola: Nazwa roli (np. 'planista', 'admin')

    Returns:
        Lista słowników z polami: id, user_id, login, endpoint, p256dh, auth
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            "WHERE rola = %s AND is_active = 1",
            (rola,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows or []
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_role error: %s", e)
        return []


def get_push_subscriptions_for_roles(roles: list) -> list:
    """Pobierz aktywne subskrypcje push dla listy ról (bez duplikatów urządzeń).

    Args:
        roles: Lista nazw ról

    Returns:
        Lista unikalnych subskrypcji (po endpoint) dla podanych ról
    """
    if not roles:
        return []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        placeholders = ', '.join(['%s'] * len(roles))
        cursor.execute(
            f"SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            f"WHERE rola IN ({placeholders}) AND is_active = 1",
            tuple(roles)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        # Deduplicate by endpoint
        seen = set()
        result = []
        for row in (rows or []):
            ep = row['endpoint']
            if ep not in seen:
                seen.add(ep)
                result.append(row)
        return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_roles error: %s", e)
        return []


def get_push_subscriptions_for_login(login: str) -> list:
    """Pobierz aktywne subskrypcje push dla konkretnego loginu.

    Args:
        login: Login użytkownika

    Returns:
        Lista subskrypcji dla danego loginu
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, login, endpoint, p256dh, auth FROM push_subskrypcje "
            "WHERE login = %s AND is_active = 1",
            (login,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows or []
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("[PUSH-DB] get_push_subscriptions_for_login error: %s", e)
        return []
