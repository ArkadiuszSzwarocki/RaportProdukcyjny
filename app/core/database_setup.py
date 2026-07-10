"""
Moduł inicjalizacyjny i migracyjny bazy danych.
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
from app.core.database import get_db_connection, get_table_name, set_active_database_name

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
            data_produkcji DATE DEFAULT NULL,
            rodzaj_palety VARCHAR(50) DEFAULT 'krajowa'
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
            data_produkcji DATE DEFAULT NULL,
            rodzaj_palety VARCHAR(50) DEFAULT 'krajowa'
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
        CREATE TABLE IF NOT EXISTS czyszczenie_separatorow (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(50) NOT NULL,
            data_planu DATE NOT NULL,
            data_wykonania DATETIME NULL,
            login_wykonawcy VARCHAR(100) NULL,
            status VARCHAR(20) DEFAULT 'pending',
            komentarz TEXT NULL,
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
            nr_palety VARCHAR(100) DEFAULT NULL,
            nr_plomby VARCHAR(100) DEFAULT NULL,
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
            nr_palety VARCHAR(100) DEFAULT NULL,
            nr_plomby VARCHAR(100) DEFAULT NULL,
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
            nr_palety VARCHAR(100) DEFAULT NULL,
            nr_plomby VARCHAR(100) DEFAULT NULL,
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
            nr_palety VARCHAR(100) DEFAULT NULL,
            nr_plomby VARCHAR(100) DEFAULT NULL,
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS slownik_surowcow (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(255) NOT NULL UNIQUE,
            symbol VARCHAR(50) DEFAULT NULL,
            typ VARCHAR(50) DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)


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

    # Tabela składników receptury AGRO — powiązana przez nr_receptury z produkty_receptury
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receptury_agro_skladniki (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            nr_receptury    VARCHAR(64) NOT NULL,
            nazwa_produktu  VARCHAR(100) NOT NULL,
            kolejnosc       INT DEFAULT 0,
            skladnik_nazwa  VARCHAR(255) NOT NULL,
            ilosc_kg_szarza FLOAT NULL DEFAULT NULL,
            typ             VARCHAR(50) DEFAULT 'surowiec',
            aktywny         TINYINT(1) DEFAULT 1,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_receptury_agro_nr (nr_receptury),
            INDEX idx_receptury_agro_aktywny (aktywny)
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
        CREATE TABLE IF NOT EXISTS magazyn_dozwolone_lokalizacje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nazwa VARCHAR(100) NOT NULL UNIQUE,
            opis VARCHAR(255) DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Inicjalizacja domyślnych lokalizacji
    cursor.execute("SELECT COUNT(*) as count FROM magazyn_dozwolone_lokalizacje")
    if cursor.fetchone()[0] == 0:
        default_locs = [
            'R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07',
            'MP01', 'MS01', 'BF_MS01', 'BF_MP01', 
            'MGW01', 'MGW02', 'MOP01', 'MDO01'
        ]
        # Dodajemy K001 do K050
        for i in range(1, 51):
            default_locs.append(f"K{i:03d}")
            
        for loc in default_locs:
            cursor.execute("INSERT INTO magazyn_dozwolone_lokalizacje (nazwa) VALUES (%s)", (loc,))

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
            aktywna TINYINT(1) DEFAULT 1,
            typ_drukarki VARCHAR(50) DEFAULT 'etykiet'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS przypisania_raportow (
            id INT AUTO_INCREMENT PRIMARY KEY,
            typ_raportu VARCHAR(100) NOT NULL UNIQUE,
            nazwa_raportu VARCHAR(255) NOT NULL,
            nazwa_drukarki VARCHAR(255) DEFAULT '',
            aktywne TINYINT(1) DEFAULT 0
        )
    """)
    
    # Initialize default reports if not exists
    cursor.execute("SELECT id FROM przypisania_raportow WHERE typ_raportu = 'raport_palet_agro'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO przypisania_raportow (typ_raportu, nazwa_raportu, aktywne) VALUES ('raport_palet_agro', 'Raport Palet (Zakończenie Zlecenia AGRO)', 0)")

    cursor.execute("SELECT id FROM przypisania_raportow WHERE typ_raportu = 'raport_dostawy_zewnetrznej'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO przypisania_raportow (typ_raportu, nazwa_raportu, aktywne) VALUES ('raport_dostawy_zewnetrznej', 'Raport Dostawy Zewnętrznej (Przyjęcia)', 0)")

    cursor.execute("SELECT id FROM przypisania_raportow WHERE typ_raportu = 'raport_przesuniecia'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO przypisania_raportow (typ_raportu, nazwa_raportu, aktywne) VALUES ('raport_przesuniecia', 'Raport Przesunięcia (Ruchy)', 0)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produkcja_inwentaryzacja_sesje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            typ VARCHAR(10) NOT NULL DEFAULT 'BB_MZ',
            status VARCHAR(20) DEFAULT 'OPEN',
            created_by VARCHAR(100),
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME NULL,
            INDEX idx_prod_inv_status (status),
            INDEX idx_prod_inv_typ (typ)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produkcja_inwentaryzacja_wpisy (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sesja_id INT NOT NULL,
            zbiornik VARCHAR(20) NOT NULL,
            nazwa VARCHAR(255) DEFAULT '',
            nr_partii VARCHAR(100) DEFAULT '',
            waga DECIMAL(12,2) DEFAULT 0,
            komentarz TEXT,
            user_login VARCHAR(100),
            data_wpisu DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sesja_id) REFERENCES produkcja_inwentaryzacja_sesje(id) ON DELETE CASCADE,
            INDEX idx_prod_inv_wpisy_sesja (sesja_id),
            UNIQUE KEY uq_prod_inv_wpisy_zbiornik (sesja_id, zbiornik)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_inwentaryzacja_produkcji_sesje (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(10) DEFAULT 'AGRO',
            status VARCHAR(20) DEFAULT 'OPEN',
            created_by VARCHAR(100),
            lokalizacja VARCHAR(100) DEFAULT 'WSZYSTKO',
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME NULL,
            INDEX idx_mag_prod_inv_status (status),
            INDEX idx_mag_prod_inv_linia (linia)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS magazyn_inwentaryzacja_produkcji_wpisy (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sesja_id INT NOT NULL,
            ruch_id INT NULL,
            old_ruch_id INT NULL,
            zbiornik VARCHAR(20) NOT NULL,
            surowiec_nazwa VARCHAR(255) DEFAULT '',
            waga_systemowa DECIMAL(12,2) DEFAULT 0,
            waga_faktyczna DECIMAL(12,2) DEFAULT 0,
            user_login VARCHAR(100),
            data_wpisu DATETIME DEFAULT CURRENT_TIMESTAMP,
            paleta_id INT NULL,
            nr_palety VARCHAR(100) DEFAULT '',
            nr_partii VARCHAR(100) DEFAULT '',
            data_produkcji DATE NULL,
            data_przydatnosci DATE NULL,
            FOREIGN KEY (sesja_id) REFERENCES magazyn_inwentaryzacja_produkcji_sesje(id) ON DELETE CASCADE,
            INDEX idx_mag_prod_inv_wpisy_sesja (sesja_id),
            UNIQUE KEY uq_mag_prod_inv_wpisy_zbiornik (sesja_id, zbiornik)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS czyszczenie_magnesow (
            id INT AUTO_INCREMENT PRIMARY KEY,
            linia VARCHAR(10) NOT NULL,
            data_planu DATE NOT NULL,
            data_wykonania DATETIME NULL,
            login_wykonawcy VARCHAR(100) NULL,
            status VARCHAR(20) DEFAULT 'pending',
            komentarz TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_czyszczenie_magnesow_data_linia (data_planu, linia)
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
    _add_column_if_missing(cursor, "plan_produkcji", "odrzuty_przesiewacz", "FLOAT DEFAULT 0", "Dodawanie kolumny 'odrzuty_przesiewacz'")
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
    _add_column_if_missing(cursor, "plan_produkcji_agro", "odrzuty_przesiewacz", "FLOAT DEFAULT 0", "Dodawanie kolumny 'odrzuty_przesiewacz' (AGRO)")
    
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
    _add_column_if_missing(cursor, "palety_workowanie", "nr_plomby", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_plomby' do palety_workowanie")
    _add_column_if_missing(cursor, "palety_agro", "nr_plomby", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_plomby' do palety_agro")

    # aktywne_sesje columns
    _add_column_if_missing(cursor, "aktywne_sesje", "ip_address", "VARCHAR(64) NULL", "Dodawanie kolumny 'ip_address' do aktywne_sesje")

    # magazyn_palety_agro columns
    _add_column_if_missing(cursor, "magazyn_palety", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do magazyn_palety")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "nr_palety", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_palety' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety", "nr_plomby", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_plomby' do magazyn_palety")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "nr_plomby", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_plomby' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "linia", "VARCHAR(20) DEFAULT 'AGRO'", "Dodawanie kolumny 'linia' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "user_login", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'user_login' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "data_potwierdzenia", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'data_potwierdzenia' do magazyn_palety_agro")
    _add_column_if_missing(cursor, "magazyn_palety_agro", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'created_at' do magazyn_palety_agro")
    
    _add_column_if_missing(cursor, "drukarki", "typ_drukarki", "VARCHAR(50) DEFAULT 'etykiet'", "Dodawanie kolumny 'typ_drukarki' do drukarki")
    
    # agro_mix_rozliczenie columns
    _add_column_if_missing(cursor, "agro_mix_rozliczenie", "zuzyte_kiedy", "DATETIME NULL", "Dodawanie kolumny 'zuzyte_kiedy' do agro_mix_rozliczenie")

    # agro_workowanie_rozliczenie — rozszerzenie o straty, liczniki MQTT i typ zdarzenia (Folio flow)
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "straty_worki", "FLOAT DEFAULT 0", "Dodawanie kolumny 'straty_worki' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "licznik_start", "INT DEFAULT 0", "Dodawanie kolumny 'licznik_start' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "licznik_stop", "INT DEFAULT 0", "Dodawanie kolumny 'licznik_stop' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "pozostalo_na_rolce", "FLOAT DEFAULT 0", "Dodawanie kolumny 'pozostalo_na_rolce' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "lokalizacja_zwrotu", "VARCHAR(100) DEFAULT NULL", "Dodawanie kolumny 'lokalizacja_zwrotu' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "typ_zdarzenia", "VARCHAR(30) DEFAULT 'ROZLICZENIE'", "Dodawanie kolumny 'typ_zdarzenia' do agro_workowanie_rozliczenie")
    _add_column_if_missing(cursor, "agro_workowanie_rozliczenie", "link_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'link_id' (FK do agro_plan_opakowania) do agro_workowanie_rozliczenie")

    # agro_plan_opakowania — licznik MQTT przy wsadzeniu rolki
    _add_column_if_missing(cursor, "agro_plan_opakowania", "licznik_start", "INT DEFAULT 0", "Dodawanie kolumny 'licznik_start' (MQTT) do agro_plan_opakowania")
    
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

    # Inwentaryzacja produkcji (AGRO) columns
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_sesje", "linia", "VARCHAR(10) DEFAULT 'AGRO'", "Dodawanie kolumny 'linia' do sesji inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_sesje", "lokalizacja", "VARCHAR(100) DEFAULT 'WSZYSTKO'", "Dodawanie kolumny 'lokalizacja' do sesji inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_sesje", "comment", "TEXT", "Dodawanie kolumny 'comment' do sesji inwentaryzacji produkcji")

    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "ruch_id", "INT NULL", "Dodawanie kolumny 'ruch_id' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "old_ruch_id", "INT NULL", "Dodawanie kolumny 'old_ruch_id' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "surowiec_nazwa", "VARCHAR(255) DEFAULT ''", "Dodawanie kolumny 'surowiec_nazwa' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "waga_systemowa", "DECIMAL(12,2) DEFAULT 0", "Dodawanie kolumny 'waga_systemowa' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "waga_faktyczna", "DECIMAL(12,2) DEFAULT 0", "Dodawanie kolumny 'waga_faktyczna' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "data_wpisu", "DATETIME DEFAULT CURRENT_TIMESTAMP", "Dodawanie kolumny 'data_wpisu' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "paleta_id", "INT NULL", "Dodawanie kolumny 'paleta_id' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "nr_palety", "VARCHAR(100) DEFAULT ''", "Dodawanie kolumny 'nr_palety' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "nr_partii", "VARCHAR(100) DEFAULT ''", "Dodawanie kolumny 'nr_partii' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "data_produkcji", "DATE NULL", "Dodawanie kolumny 'data_produkcji' do wpisów inwentaryzacji produkcji")
    _add_column_if_missing(cursor, "magazyn_inwentaryzacja_produkcji_wpisy", "data_przydatnosci", "DATE NULL", "Dodawanie kolumny 'data_przydatnosci' do wpisów inwentaryzacji produkcji")

    _ensure_unique_index(
        cursor,
        "magazyn_inwentaryzacja_produkcji_wpisy",
        "uq_mag_prod_inv_wpisy_zbiornik",
        ["sesja_id", "zbiornik"],
        "Unikalny indeks (sesja_id, zbiornik) dla inwentaryzacji produkcji",
    )

    # Własna data produkcji dla planów
    _add_column_if_missing(cursor, "plan_produkcji", "data_produkcji", "DATE DEFAULT NULL", "Dodawanie kolumny 'data_produkcji' (PSD)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "data_produkcji", "DATE DEFAULT NULL", "Dodawanie kolumny 'data_produkcji' (AGRO)")
    
    # Typ opakowania (worki/bigbag) dla workownia - określa czy pokazywać pola folii/etykiet
    _add_column_if_missing(cursor, "plan_produkcji", "typ_opakowania", "VARCHAR(20) DEFAULT 'worki'", "Dodawanie kolumny 'typ_opakowania' (PSD)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "typ_opakowania", "VARCHAR(20) DEFAULT 'worki'", "Dodawanie kolumny 'typ_opakowania' (AGRO)")
    
    _add_column_if_missing(cursor, "plan_produkcji_agro", "opakowanie_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'opakowanie_id' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "etykieta_id", "INT NULL DEFAULT NULL", "Dodawanie kolumny 'etykieta_id' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_operator_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'start_checklist_operator_login' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_operator_at", "DATETIME NULL", "Dodawanie kolumny 'start_checklist_operator_at' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_quality_login", "VARCHAR(100) NULL", "Dodawanie kolumny 'start_checklist_quality_login' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "start_checklist_quality_at", "DATETIME NULL", "Dodawanie kolumny 'start_checklist_quality_at' (AGRO)")
    _add_column_if_missing(cursor, "plan_produkcji_agro", "nr_partii", "VARCHAR(100) NULL", "Dodawanie kolumny 'nr_partii' - numer partii produkcji (AGRO)")

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

    # Performance indexes for dashboard queries
    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji WHERE Key_name = 'idx_plan_data_status_deleted'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji ADD INDEX idx_plan_data_status_deleted (data_planu, status, is_deleted)")
            print("[OK] Added composite index idx_plan_data_status_deleted to plan_produkcji")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_data_status_deleted: {e}")

    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji_agro WHERE Key_name = 'idx_plan_agro_data_status_deleted'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji_agro ADD INDEX idx_plan_agro_data_status_deleted (data_planu, status, is_deleted)")
            print("[OK] Added composite index idx_plan_agro_data_status_deleted to plan_produkcji_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_agro_data_status_deleted: {e}")

    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji WHERE Key_name = 'idx_plan_sekcja_data'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji ADD INDEX idx_plan_sekcja_data (sekcja, data_planu, status)")
            print("[OK] Added composite index idx_plan_sekcja_data to plan_produkcji")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_sekcja_data: {e}")

    try:
        cursor.execute("SHOW INDEX FROM plan_produkcji_agro WHERE Key_name = 'idx_plan_agro_sekcja_data'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji_agro ADD INDEX idx_plan_agro_sekcja_data (sekcja, data_planu, status)")
            print("[OK] Added composite index idx_plan_agro_sekcja_data to plan_produkcji_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_plan_agro_sekcja_data: {e}")

    # Indexes for bufor queries
    try:
        cursor.execute("SHOW INDEX FROM bufor WHERE Key_name = 'idx_bufor_data_status'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE bufor ADD INDEX idx_bufor_data_status (data_planu, status, linia)")
            print("[OK] Added composite index idx_bufor_data_status to bufor")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_bufor_data_status: {e}")

    try:
        cursor.execute("SHOW INDEX FROM bufor_agro WHERE Key_name = 'idx_bufor_agro_data_status'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE bufor_agro ADD INDEX idx_bufor_agro_data_status (data_planu, status)")
            print("[OK] Added composite index idx_bufor_agro_data_status to bufor_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_bufor_agro_data_status: {e}")

    # Additional performance indexes for AGRO workowanie page
    try:
        cursor.execute("SHOW INDEX FROM palety_agro WHERE Key_name = 'idx_palety_agro_plan_id'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE palety_agro ADD INDEX idx_palety_agro_plan_id (plan_id)")
            print("[OK] Added index idx_palety_agro_plan_id to palety_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_palety_agro_plan_id: {e}")

    try:
        cursor.execute("SHOW INDEX FROM agro_workowanie_rozliczenie WHERE Key_name = 'idx_agro_work_rozl_plan'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE agro_workowanie_rozliczenie ADD INDEX idx_agro_work_rozl_plan (plan_id, created_at)")
            print("[OK] Added index idx_agro_work_rozl_plan to agro_workowanie_rozliczenie")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_agro_work_rozl_plan: {e}")

    try:
        cursor.execute("SHOW INDEX FROM magazyn_opakowania WHERE Key_name = 'idx_maga_opak_linia'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE magazyn_opakowania ADD INDEX idx_maga_opak_linia (linia)")
            print("[OK] Added index idx_maga_opak_linia to magazyn_opakowania")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_maga_opak_linia: {e}")

    try:
        cursor.execute("SHOW INDEX FROM dziennik_zmiany WHERE Key_name = 'idx_dziennik_data_linia'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE dziennik_zmiany ADD INDEX idx_dziennik_data_linia (data_wpisu, sekcja)")
            print("[OK] Added index idx_dziennik_data_linia to dziennik_zmiany")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_dziennik_data_linia: {e}")

    try:
        cursor.execute("SHOW INDEX FROM szarze_agro WHERE Key_name = 'idx_szarze_agro_plan'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE szarze_agro ADD INDEX idx_szarze_agro_plan (plan_id, data_dodania)")
            print("[OK] Added index idx_szarze_agro_plan to szarze_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_szarze_agro_plan: {e}")

    try:
        cursor.execute("SHOW INDEX FROM dosypki_agro WHERE Key_name = 'idx_dosypki_agro_plan'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE dosypki_agro ADD INDEX idx_dosypki_agro_plan (plan_id, szarza_id)")
            print("[OK] Added index idx_dosypki_agro_plan to dosypki_agro")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_dosypki_agro_plan: {e}")

    try:
        cursor.execute("SHOW INDEX FROM agro_mix_rozliczenie WHERE Key_name = 'idx_agro_mix_zuzyte'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE agro_mix_rozliczenie ADD INDEX idx_agro_mix_zuzyte (zuzyte_w_id)")
            print("[OK] Added index idx_agro_mix_zuzyte to agro_mix_rozliczenie")
    except Exception as e:
        print(f"[WARN] Failed to add index idx_agro_mix_zuzyte: {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM plan_produkcji LIKE 'rodzaj_palety'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji ADD COLUMN rodzaj_palety VARCHAR(50) DEFAULT 'krajowa'")
            print("[OK] Added column rodzaj_palety to plan_produkcji")
    except Exception as e:
        print(f"[WARN] Failed to add column rodzaj_palety to plan_produkcji: {e}")

    try:
        cursor.execute("SHOW COLUMNS FROM plan_produkcji_agro LIKE 'rodzaj_palety'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE plan_produkcji_agro ADD COLUMN rodzaj_palety VARCHAR(50) DEFAULT 'krajowa'")
            print("[OK] Added column rodzaj_palety to plan_produkcji_agro")
    except Exception as e:
        print(f"[WARN] Failed to add column rodzaj_palety to plan_produkcji_agro: {e}")



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
        from app.repositories.production_repository import refresh_bufor_queue
        refresh_bufor_queue(linia='PSD')
        refresh_bufor_queue(linia='AGRO')
        
    except Exception as e:
        print(f"[ERROR] Blad podczas inicjalizacji bazy danych: {e}")
        raise

