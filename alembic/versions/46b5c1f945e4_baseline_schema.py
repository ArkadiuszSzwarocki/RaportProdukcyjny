"""baseline_schema

Revision ID: 46b5c1f945e4
Revises: 
Create Date: 2026-07-17 23:09:06.527413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46b5c1f945e4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE `agro_mix_rozliczenie` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_planu` date NOT NULL,
      `poprzednie_zlecenie_id` int(11) DEFAULT NULL,
      `nazwa_mix` varchar(255) NOT NULL,
      `ilosc_workow` int(11) NOT NULL,
      `waga_kg` float NOT NULL,
      `autor_login` varchar(50) DEFAULT NULL,
      `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
      `nastepne_zlecenie_id` int(11) DEFAULT NULL,
      `kategoria` varchar(20) DEFAULT 'DO_LNU',
      `status` varchar(20) DEFAULT 'DOSTEPNY',
      `zuzyte_w_id` int(11) DEFAULT NULL,
      `zuzyte_kiedy` datetime DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_agro_mix_zuzyte` (`zuzyte_w_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `agro_plan_opakowania` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `opakowanie_id` int(11) NOT NULL,
      `stan_poczatkowy` decimal(10,2) DEFAULT NULL,
      `stan_koncowy` decimal(10,2) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `is_active` tinyint(1) DEFAULT 1,
      `is_carryover` tinyint(1) DEFAULT 0,
      `licznik_start` int(11) DEFAULT 0,
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=67 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `agro_stanowiska` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(100) NOT NULL,
      `typ` varchar(50) DEFAULT NULL,
      `is_locked` tinyint(1) DEFAULT 0,
      `current_pallet_id` int(11) DEFAULT NULL,
      `current_plan_id` int(11) DEFAULT NULL,
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`)
    ) ENGINE=MyISAM AUTO_INCREMENT=27 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `agro_workowanie_rozliczenie` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `data_planu` date NOT NULL,
      `produkt` varchar(100) NOT NULL,
      `opakowanie_id` int(11) DEFAULT NULL,
      `opakowanie_nazwa` varchar(255) NOT NULL,
      `stan_przed` float DEFAULT 0,
      `wyprodukowano_szt` int(11) DEFAULT 0,
      `szt_na_palecie` int(11) DEFAULT 0,
      `kg_na_worek` float DEFAULT 20,
      `palety_kg_wykonane` float DEFAULT 0,
      `zuzyte_worki` float DEFAULT 0,
      `stan_po` float DEFAULT 0,
      `autor_login` varchar(100) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `straty_worki` float DEFAULT 0,
      `licznik_start` int(11) DEFAULT 0,
      `licznik_stop` int(11) DEFAULT 0,
      `pozostalo_na_rolce` float DEFAULT 0,
      `lokalizacja_zwrotu` varchar(100) DEFAULT NULL,
      `typ_zdarzenia` varchar(30) DEFAULT 'ROZLICZENIE',
      `link_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_agro_work_rozl_data` (`data_planu`),
      KEY `idx_agro_work_rozl_plan` (`plan_id`),
      KEY `opakowanie_id` (`opakowanie_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=110 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `aktywne_sesje` (
      `session_id` varchar(64) NOT NULL,
      `user_id` int(11) NOT NULL,
      `login` varchar(50) NOT NULL,
      `rola` varchar(20) DEFAULT '',
      `pracownik_id` int(11) DEFAULT NULL,
      `display_name` varchar(100) DEFAULT NULL,
      `last_path` varchar(255) DEFAULT NULL,
      `logged_in_at` datetime DEFAULT current_timestamp(),
      `last_seen` datetime DEFAULT current_timestamp(),
      `is_active` tinyint(1) DEFAULT 1,
      `ip_address` varchar(64) DEFAULT NULL,
      PRIMARY KEY (`session_id`),
      KEY `idx_aktywne_sesje_seen` (`is_active`,`last_seen`),
      KEY `idx_aktywne_sesje_user` (`user_id`,`is_active`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `app_instance_heartbeat` (
      `instance_id` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
      `hostname` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL,
      `pid` int(11) NOT NULL,
      `component` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
      `status` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
      `started_at` datetime NOT NULL,
      `last_heartbeat` datetime NOT NULL,
      `extra` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      PRIMARY KEY (`instance_id`),
      KEY `idx_component_heartbeat` (`component`,`last_heartbeat`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `backup_magazyn_palety_agro_dup_20260519_batch` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `paleta_workowanie_id` int(11) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `data_planu` date DEFAULT NULL,
      `produkt` varchar(100) DEFAULT NULL,
      `waga_netto` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `tara` float DEFAULT 0,
      `user_login` varchar(100) DEFAULT NULL,
      `data_potwierdzenia` datetime DEFAULT current_timestamp(),
      `created_at` datetime DEFAULT current_timestamp(),
      `lokalizacja` varchar(100) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(20) DEFAULT 'AGRO',
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_magazyn_palety_agro_paleta_workowanie` (`paleta_workowanie_id`),
      KEY `plan_id` (`plan_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=57 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `backup_palety_agro_dup_20260519_batch` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `waga` float NOT NULL,
      `data_dodania` timestamp NOT NULL DEFAULT current_timestamp(),
      `tara` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `status` varchar(32) DEFAULT 'do_przyjecia',
      `data_potwierdzenia` datetime DEFAULT NULL,
      `czas_potwierdzenia_s` int(11) DEFAULT NULL,
      `czas_rzeczywistego_potwierdzenia` time DEFAULT NULL,
      `waga_potwierdzona` float DEFAULT NULL,
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `dodal_login` varchar(50) DEFAULT NULL,
      `potwierdzil_login` varchar(50) DEFAULT NULL,
      `nr_palety` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `plan_id` (`plan_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=76 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `bufor` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `zasyp_id` int(11) NOT NULL,
      `data_planu` date NOT NULL,
      `linia` varchar(20) DEFAULT 'PSD',
      `produkt` varchar(100) NOT NULL,
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `typ_produkcji` varchar(20) DEFAULT 'worki_zgrzewane_25',
      `tonaz_rzeczywisty` float DEFAULT 0,
      `spakowano` float DEFAULT 0,
      `kolejka` int(11) NOT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `status` varchar(20) DEFAULT 'aktywny',
      PRIMARY KEY (`id`),
      UNIQUE KEY `bufor_uq_data_produkt_kolejka` (`data_planu`,`produkt`,`kolejka`),
      KEY `zasyp_id` (`zasyp_id`),
      KEY `idx_bufor_data_status` (`data_planu`,`status`,`linia`)
    ) ENGINE=MyISAM AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `bufor_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `zasyp_id` int(11) NOT NULL,
      `data_planu` date NOT NULL,
      `produkt` varchar(100) NOT NULL,
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `typ_produkcji` varchar(20) DEFAULT 'agro',
      `tonaz_rzeczywisty` float DEFAULT 0,
      `spakowano` float DEFAULT 0,
      `kolejka` int(11) NOT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `status` varchar(20) DEFAULT 'aktywny',
      PRIMARY KEY (`id`),
      UNIQUE KEY `bufor_agro_uq_data_produkt_kolejka` (`data_planu`,`produkt`,`kolejka`),
      KEY `zasyp_id` (`zasyp_id`),
      KEY `idx_bufor_agro_data_status` (`data_planu`,`status`)
    ) ENGINE=MyISAM AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `czyszczenie_magnesow` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
      `data_planu` date NOT NULL,
      `data_wykonania` datetime DEFAULT NULL,
      `login_wykonawcy` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
      `komentarz` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_czyszczenie_magnesow_data_linia` (`data_planu`,`linia`)
    ) ENGINE=MyISAM AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `czyszczenie_separatorow` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
      `data_planu` date NOT NULL,
      `data_wykonania` datetime DEFAULT NULL,
      `login_wykonawcy` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
      `komentarz` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `dosypki` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `nazwa` varchar(255) NOT NULL,
      `kg` float NOT NULL,
      `data_zlecenia` datetime DEFAULT current_timestamp(),
      `pracownik_id` int(11) DEFAULT NULL,
      `potwierdzone` tinyint(1) DEFAULT 0,
      `potwierdzil_pracownik_id` int(11) DEFAULT NULL,
      `data_potwierdzenia` datetime DEFAULT NULL,
      `szarza_id` int(11) DEFAULT NULL,
      `anulowana` tinyint(1) DEFAULT 0,
      `data_anulowania` datetime DEFAULT NULL,
      `anulowal_login` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `plan_id` (`plan_id`),
      KEY `pracownik_id` (`pracownik_id`),
      KEY `potwierdzil_pracownik_id` (`potwierdzil_pracownik_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=67 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `dosypki_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `szarza_id` int(11) DEFAULT NULL,
      `nazwa` varchar(255) NOT NULL,
      `kg` float NOT NULL,
      `data_zlecenia` datetime DEFAULT current_timestamp(),
      `pracownik_id` int(11) DEFAULT NULL,
      `potwierdzone` tinyint(1) DEFAULT 0,
      `potwierdzil_pracownik_id` int(11) DEFAULT NULL,
      `data_potwierdzenia` datetime DEFAULT NULL,
      `anulowana` tinyint(1) DEFAULT 0,
      `data_anulowania` datetime DEFAULT NULL,
      `anulowal_login` varchar(100) DEFAULT NULL,
      `pracownik_login` varchar(50) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`),
      KEY `potwierdzil_pracownik_id` (`potwierdzil_pracownik_id`),
      KEY `idx_dosypki_agro_plan` (`plan_id`,`szarza_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=32 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `drukarki` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `ip` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `lokalizacja` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '',
      `aktywna` tinyint(1) DEFAULT 1,
      `typ_drukarki` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'etykiet',
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `dur_komentarze` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `awaria_id` int(11) NOT NULL,
      `autor_id` int(11) DEFAULT NULL,
      `tresc` text NOT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `awaria_id` (`awaria_id`),
      KEY `autor_id` (`autor_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `dzialy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `lider_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`)
    ) ENGINE=MyISAM AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `dziennik_zmian_statusu` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `awaria_id` int(11) NOT NULL,
      `stary_status` varchar(30) DEFAULT NULL,
      `nowy_status` varchar(30) NOT NULL,
      `zmieniony_przez` int(11) DEFAULT NULL,
      `data_zmiany` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `awaria_id` (`awaria_id`),
      KEY `zmieniony_przez` (`zmieniony_przez`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `dziennik_zmiany` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_wpisu` date NOT NULL,
      `linia` varchar(20) DEFAULT 'PSD',
      `sekcja` varchar(50) NOT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `problem` text DEFAULT NULL,
      `status` varchar(20) DEFAULT 'roboczy',
      `czas_start` time DEFAULT NULL,
      `czas_stop` time DEFAULT NULL,
      `kategoria` varchar(50) DEFAULT NULL,
      `status_zglosnienia` varchar(30) DEFAULT 'zgloszone',
      `data_zakonczenia` date DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`),
      KEY `idx_dziennik_data_linia` (`data_wpisu`,`sekcja`)
    ) ENGINE=MyISAM AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_agro_opakowania` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_agro_opakowania_lokal` (`lokalizacja`),
      KEY `idx_magazyn_agro_opakowania_nazwa` (`nazwa`(250)),
      KEY `idx_magazyn_agro_opakowania_lokal` (`lokalizacja`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_agro_ruch` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `surowiec_id` int(11) DEFAULT NULL,
      `surowiec_nazwa` varchar(255) DEFAULT NULL,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `typ_ruchu` varchar(50) DEFAULT NULL,
      `ilosc` float DEFAULT NULL,
      `ilosc_po` float DEFAULT NULL,
      `status` varchar(20) DEFAULT 'POTWIERDZONE',
      `autor_login` varchar(100) DEFAULT NULL,
      `autor_data` datetime DEFAULT current_timestamp(),
      `potwierdzil_login` varchar(100) DEFAULT NULL,
      `potwierdzil_data` datetime DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `zbiornik` varchar(100) DEFAULT NULL,
      `ruch_zrodlowy_id` int(11) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      PRIMARY KEY (`id`),
      KEY `idx_agro_ruch_surowiec` (`surowiec_id`),
      KEY `idx_agro_ruch_status` (`status`)
    ) ENGINE=MyISAM AUTO_INCREMENT=433 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_agro_slownik_surowce` (
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `id` int(11) NOT NULL AUTO_INCREMENT,
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`)
    ) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_agro_surowce` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_agro_surowce_lokal` (`lokalizacja`),
      KEY `idx_magazyn_agro_surowce_nazwa` (`nazwa`(250)),
      KEY `idx_magazyn_agro_surowce_lokal` (`lokalizacja`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_archiwum` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `original_id` int(11) DEFAULT NULL,
      `nr_palety` varchar(50) DEFAULT NULL,
      `nazwa` varchar(255) DEFAULT NULL,
      `typ_palety` varchar(50) DEFAULT NULL,
      `linia` varchar(10) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `waga_ostatnia` float DEFAULT NULL,
      `lokalizacja_ostatnia` varchar(100) DEFAULT NULL,
      `data_archiwizacji` datetime DEFAULT current_timestamp(),
      `user_login` varchar(100) DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=103 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_dodatki` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `nazwa` varchar(255) NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(10) DEFAULT 'PSD',
      `jednostka` varchar(20) DEFAULT NULL,
      `min_stan` float DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_magazyn_nazwa` (`nazwa`(250)),
      KEY `idx_magazyn_lokal` (`lokalizacja`)
    ) ENGINE=MyISAM AUTO_INCREMENT=373 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_dostawy` (
      `id` varchar(50) NOT NULL,
      `order_ref` varchar(100) DEFAULT NULL,
      `supplier` varchar(100) DEFAULT NULL,
      `delivery_date` date DEFAULT NULL,
      `status` varchar(50) DEFAULT NULL,
      `items` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`items`)),
      `created_by` varchar(50) DEFAULT NULL,
      `created_at` datetime DEFAULT NULL,
      `requires_lab` tinyint(1) DEFAULT 0,
      `linia` varchar(10) DEFAULT NULL,
      `lokalizacja_z` varchar(50) DEFAULT NULL,
      `lokalizacja_do` varchar(50) DEFAULT NULL,
      `potwierdzone_przez` varchar(50) DEFAULT NULL,
      `potwierdzone_at` datetime DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_dozwolone_lokalizacje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `opis` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '',
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`)
    ) ENGINE=MyISAM AUTO_INCREMENT=66 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_inwentaryzacja_produkcji_sesje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL,
      `status` enum('OPEN','CLOSED','APPLIED') COLLATE utf8mb4_unicode_ci DEFAULT 'OPEN',
      `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `closed_at` datetime DEFAULT NULL,
      `comment` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `lokalizacja` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT 'Wszystko',
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_inwentaryzacja_produkcji_wpisy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `sesja_id` int(11) NOT NULL,
      `ruch_id` int(11) DEFAULT NULL,
      `zbiornik` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `surowiec_nazwa` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `waga_systemowa` float DEFAULT 0,
      `waga_faktyczna` float DEFAULT 0,
      `data_wpisu` datetime DEFAULT current_timestamp(),
      `user_login` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `paleta_id` int(11) DEFAULT NULL,
      `nr_palety` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `nr_partii` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `old_ruch_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_mag_prod_inv_wpisy_zbiornik` (`sesja_id`,`zbiornik`)
    ) ENGINE=MyISAM AUTO_INCREMENT=226 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `magazyn_inwentaryzacja_sesje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(10) NOT NULL,
      `status` enum('OPEN','CLOSED','APPLIED') DEFAULT 'OPEN',
      `created_by` varchar(100) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `closed_at` datetime DEFAULT NULL,
      `comment` text DEFAULT NULL,
      `lokalizacja` varchar(100) DEFAULT 'Wszystko',
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_inwentaryzacja_wpisy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `sesja_id` int(11) NOT NULL,
      `paleta_id` int(11) DEFAULT NULL,
      `nr_palety` varchar(50) DEFAULT NULL,
      `typ_palety` enum('surowiec','opakowanie','wyrˇb gotowy') DEFAULT NULL,
      `nazwa` varchar(255) DEFAULT NULL,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `waga_systemowa` float DEFAULT 0,
      `waga_faktyczna` float DEFAULT 0,
      `data_wpisu` datetime DEFAULT current_timestamp(),
      `user_login` varchar(100) DEFAULT NULL,
      `linia` varchar(10) DEFAULT 'PSD',
      `typ_opakowania` varchar(50) DEFAULT 'brak',
      `jednostka` varchar(10) DEFAULT 'kg',
      PRIMARY KEY (`id`),
      KEY `idx_sesja` (`sesja_id`),
      KEY `idx_lokalizacja` (`lokalizacja`)
    ) ENGINE=MyISAM AUTO_INCREMENT=329 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_opakowania` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `nazwa` varchar(255) NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(10) DEFAULT 'PSD',
      PRIMARY KEY (`id`),
      KEY `idx_magazyn_opakowania_nazwa` (`nazwa`(250)),
      KEY `idx_magazyn_opakowania_lokal` (`lokalizacja`),
      KEY `idx_maga_opak_linia` (`linia`),
      KEY `idx_lokalizacja` (`lokalizacja`),
      KEY `idx_nr_palety` (`nr_palety`),
      KEY `idx_data_przydatnosci` (`data_przydatnosci`)
    ) ENGINE=MyISAM AUTO_INCREMENT=114 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_opakowania_historia` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `oryginalny_id` int(11) DEFAULT NULL,
      `nr_palety` varchar(50) DEFAULT NULL,
      `nazwa` varchar(255) NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(10) DEFAULT 'PSD',
      PRIMARY KEY (`id`),
      KEY `idx_moh_nazwa` (`nazwa`(250)),
      KEY `idx_moh_oryg_id` (`oryginalny_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_palety` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `paleta_workowanie_id` int(11) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `data_planu` date DEFAULT NULL,
      `produkt` varchar(100) DEFAULT NULL,
      `waga_netto` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `tara` float DEFAULT 0,
      `user_login` varchar(100) DEFAULT NULL,
      `data_potwierdzenia` datetime DEFAULT current_timestamp(),
      `created_at` datetime DEFAULT current_timestamp(),
      `lokalizacja` varchar(100) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `linia` varchar(10) DEFAULT 'PSD',
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `nr_palety_lp` int(11) DEFAULT NULL,
      `nr_plomby` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_magazyn_palety_paleta_workowanie` (`paleta_workowanie_id`),
      KEY `plan_id` (`plan_id`),
      KEY `idx_lokalizacja` (`lokalizacja`),
      KEY `idx_nr_palety` (`nr_palety`),
      KEY `idx_data_przydatnosci` (`data_przydatnosci`)
    ) ENGINE=MyISAM AUTO_INCREMENT=1139 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_palety_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `paleta_workowanie_id` int(11) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `data_planu` date DEFAULT NULL,
      `produkt` varchar(100) DEFAULT NULL,
      `waga_netto` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `tara` float DEFAULT 0,
      `user_login` varchar(100) DEFAULT NULL,
      `data_potwierdzenia` datetime DEFAULT current_timestamp(),
      `created_at` datetime DEFAULT current_timestamp(),
      `lokalizacja` varchar(100) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(20) DEFAULT 'AGRO',
      `nr_plomby` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_magazyn_palety_agro_paleta_workowanie` (`paleta_workowanie_id`),
      KEY `plan_id` (`plan_id`),
      KEY `idx_lokalizacja` (`lokalizacja`),
      KEY `idx_nr_palety` (`nr_palety`),
      KEY `idx_data_przydatnosci` (`data_przydatnosci`)
    ) ENGINE=MyISAM AUTO_INCREMENT=164 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_pojemnosci` (
      `sekcja` varchar(64) NOT NULL,
      `pojemnosc_max` int(11) DEFAULT 100,
      PRIMARY KEY (`sekcja`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_ruch` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `surowiec_id` int(11) DEFAULT NULL,
      `surowiec_nazwa` varchar(255) DEFAULT NULL,
      `typ_ruchu` varchar(50) DEFAULT NULL,
      `ilosc` float DEFAULT NULL,
      `ilosc_po` float DEFAULT NULL,
      `status` varchar(50) DEFAULT 'OCZEKUJACE',
      `autor_login` varchar(100) DEFAULT NULL,
      `autor_data` datetime DEFAULT NULL,
      `potwierdzil_login` varchar(100) DEFAULT NULL,
      `potwierdzil_data` datetime DEFAULT NULL,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `zbiornik` varchar(100) DEFAULT NULL,
      `ruch_zrodlowy_id` int(11) DEFAULT NULL,
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      PRIMARY KEY (`id`),
      KEY `surowiec_id` (`surowiec_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=75 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_surowce` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `nazwa` varchar(255) NOT NULL,
      `stan_magazynowy` float DEFAULT 0,
      `lokalizacja` varchar(64) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `nr_partii` varchar(100) DEFAULT NULL,
      `data_produkcji` date DEFAULT NULL,
      `data_przydatnosci` date DEFAULT NULL,
      `typ_opakowania` varchar(50) DEFAULT 'bags',
      `is_blocked` tinyint(1) DEFAULT 0,
      `linia` varchar(10) DEFAULT 'PSD',
      `jednostka` varchar(20) DEFAULT NULL,
      `min_stan` float DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_magazyn_nazwa` (`nazwa`(250)),
      KEY `idx_magazyn_lokal` (`lokalizacja`),
      KEY `idx_lokalizacja` (`lokalizacja`),
      KEY `idx_nr_palety` (`nr_palety`),
      KEY `idx_data_przydatnosci` (`data_przydatnosci`)
    ) ENGINE=MyISAM AUTO_INCREMENT=655 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `magazyn_zamowienia` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `items` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL CHECK (json_valid(`items`)),
      `status` enum('NOWE','ZAMKNIETE') NOT NULL DEFAULT 'NOWE',
      `operator_login` varchar(100) NOT NULL,
      `magazynier_login` varchar(100) DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT current_timestamp(),
      `confirmed_at` datetime DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_status` (`status`),
      KEY `idx_created` (`created_at`)
    ) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `mom_pozycje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `mom_id` int(11) NOT NULL,
      `surowiec_nazwa` varchar(255) NOT NULL,
      `przesunieto_kg` float DEFAULT 0,
      `zuzycie_kg` float DEFAULT 0,
      `roznica_kg` float DEFAULT 0,
      `komentarz` text DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `mom_id` (`mom_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `mom_rozliczenia` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `data_planu` date NOT NULL,
      `produkt` varchar(100) NOT NULL,
      `tonaz_planowany` float DEFAULT 0,
      `tonaz_rzeczywisty` float DEFAULT 0,
      `status` varchar(20) DEFAULT 'otwarty',
      `zamknal_login` varchar(100) DEFAULT NULL,
      `data_zamkniecia` datetime DEFAULT NULL,
      `uwagi` text DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `nadgodziny` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `pracownik_id` int(11) NOT NULL,
      `data` date NOT NULL,
      `ilosc_nadgodzin` float NOT NULL,
      `powod` text DEFAULT NULL,
      `status` varchar(20) DEFAULT 'pending',
      `zlozono` datetime DEFAULT current_timestamp(),
      `decyzja_dnia` datetime DEFAULT NULL,
      `lider_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `obecnosc` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_wpisu` date NOT NULL,
      `pracownik_id` int(11) NOT NULL,
      `typ` varchar(50) NOT NULL,
      `ilosc_godzin` float DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      `wyjscie_od` time DEFAULT NULL,
      `wyjscie_do` time DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `obsada_liderzy` (
      `data_wpisu` date NOT NULL,
      `lider_psd_id` int(11) DEFAULT NULL,
      `lider_agro_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`data_wpisu`),
      KEY `lider_psd_id` (`lider_psd_id`),
      KEY `lider_agro_id` (`lider_agro_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `obsada_zmiany` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_wpisu` date NOT NULL,
      `linia` varchar(20) DEFAULT 'PSD',
      `sekcja` varchar(50) NOT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `palety_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `waga` float NOT NULL,
      `data_dodania` timestamp NOT NULL DEFAULT current_timestamp(),
      `tara` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `status` varchar(32) DEFAULT 'do_przyjecia',
      `data_potwierdzenia` datetime DEFAULT NULL,
      `czas_potwierdzenia_s` int(11) DEFAULT NULL,
      `czas_rzeczywistego_potwierdzenia` time DEFAULT NULL,
      `waga_potwierdzona` float DEFAULT NULL,
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `dodal_login` varchar(50) DEFAULT NULL,
      `potwierdzil_login` varchar(50) DEFAULT NULL,
      `nr_palety` varchar(100) DEFAULT NULL,
      `nr_plomby` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_palety_agro_plan_id` (`plan_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=193 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `palety_historia` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `paleta_id` int(11) DEFAULT NULL,
      `linia` varchar(20) NOT NULL,
      `typ_palety` varchar(50) DEFAULT 'wyrob_gotowy',
      `akcja` varchar(50) NOT NULL,
      `lokalizacja_zrodlowa` varchar(100) DEFAULT NULL,
      `lokalizacja_docelowa` varchar(100) DEFAULT NULL,
      `komentarz` text DEFAULT NULL,
      `user_login` varchar(100) DEFAULT NULL,
      `data_ruchu` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=742 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `palety_workowanie` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `plan_id` int(11) NOT NULL,
      `waga` float NOT NULL,
      `data_dodania` timestamp NOT NULL DEFAULT current_timestamp(),
      `tara` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `status` varchar(32) DEFAULT 'do_przyjecia',
      `data_potwierdzenia` datetime DEFAULT NULL,
      `czas_potwierdzenia_s` int(11) DEFAULT NULL,
      `czas_rzeczywistego_potwierdzenia` time DEFAULT NULL,
      `waga_potwierdzona` float DEFAULT NULL,
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `dodal_login` varchar(100) DEFAULT NULL,
      `potwierdzil_login` varchar(128) DEFAULT NULL,
      `nr_palety_lp` int(11) DEFAULT NULL,
      `nr_plomby` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `plan_id` (`plan_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=87 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `palety_workowanie_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_palety` varchar(50) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `waga` float DEFAULT NULL,
      `tara` float DEFAULT 0,
      `waga_brutto` float DEFAULT 0,
      `status` varchar(20) DEFAULT 'do_przyjecia',
      `data_dodania` datetime DEFAULT current_timestamp(),
      `data_potwierdzenia` datetime DEFAULT NULL,
      `czas_potwierdzenia_s` int(11) DEFAULT NULL,
      `czas_rzeczywistego_potwierdzenia` time DEFAULT NULL,
      `waga_potwierdzona` float DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `plan_id` (`plan_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `plan_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_planu` date NOT NULL,
      `produkt` varchar(100) NOT NULL,
      `tonaz` float DEFAULT NULL,
      `status` varchar(20) DEFAULT 'zaplanowane',
      `real_start` datetime DEFAULT NULL,
      `real_stop` datetime DEFAULT NULL,
      `tonaz_rzeczywisty` float DEFAULT NULL,
      `kolejnosc` int(11) DEFAULT 0,
      `typ_produkcji` varchar(50) DEFAULT 'agro',
      `nr_receptury` varchar(64) DEFAULT '',
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `wyjasnienie_rozbieznosci` text DEFAULT NULL,
      `uszkodzone_worki` int(11) DEFAULT 0,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `typ_zlecenia` varchar(50) DEFAULT 'standard',
      `zasyp_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `plan_history` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) DEFAULT NULL,
      `action` varchar(50) DEFAULT NULL,
      `changes` longtext DEFAULT NULL,
      `user_login` varchar(100) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `plan_produkcji` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_planu` date NOT NULL,
      `linia` varchar(20) DEFAULT 'PSD',
      `sekcja` varchar(50) DEFAULT 'Zasyp',
      `produkt` varchar(255) NOT NULL,
      `tonaz` float NOT NULL,
      `status` varchar(20) DEFAULT 'zaplanowane',
      `real_start` datetime DEFAULT NULL,
      `real_stop` datetime DEFAULT NULL,
      `tonaz_rzeczywisty` float DEFAULT NULL,
      `kolejnosc` int(11) DEFAULT 0,
      `typ_produkcji` varchar(20) DEFAULT 'standard',
      `wyjasnienie_rozbieznosci` text DEFAULT NULL,
      `typ_zlecenia` varchar(50) DEFAULT '',
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `nr_receptury` varchar(64) DEFAULT '',
      `uszkodzone_worki` int(11) DEFAULT 0,
      `is_deleted` tinyint(1) DEFAULT 0,
      `deleted_at` datetime DEFAULT NULL,
      `zasyp_id` int(11) DEFAULT NULL,
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `start_machine_counter` int(11) DEFAULT 0,
      `sugerowana_folia` varchar(255) DEFAULT '',
      `start_pallet_counter` int(11) DEFAULT 0,
      `data_produkcji` date DEFAULT NULL,
      `typ_opakowania` varchar(20) DEFAULT 'worki',
      `skan_sscc` varchar(255) DEFAULT NULL,
      `odrzuty_przesiewacz` float DEFAULT 0,
      `rodzaj_palety` varchar(50) DEFAULT 'krajowa',
      `stop_machine_counter` int(11) DEFAULT 0,
      `stop_local_counter` int(11) DEFAULT 0,
      `termin_przydatnosci` varchar(255) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_plan_produkcji_zasyp_id` (`zasyp_id`),
      KEY `idx_plan_data_status_deleted` (`data_planu`,`status`,`is_deleted`),
      KEY `idx_plan_sekcja_data` (`sekcja`,`data_planu`,`status`)
    ) ENGINE=MyISAM AUTO_INCREMENT=266 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `plan_produkcji_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_planu` date NOT NULL,
      `sekcja` varchar(50) NOT NULL,
      `produkt` varchar(100) NOT NULL,
      `tonaz` float DEFAULT NULL,
      `status` varchar(20) DEFAULT 'zaplanowane',
      `real_start` datetime DEFAULT NULL,
      `real_stop` datetime DEFAULT NULL,
      `tonaz_rzeczywisty` float DEFAULT NULL,
      `kolejnosc` int(11) DEFAULT 0,
      `typ_produkcji` varchar(20) DEFAULT 'agro',
      `nr_receptury` varchar(64) DEFAULT '',
      `nazwa_zlecenia` varchar(255) DEFAULT '',
      `typ_zlecenia` varchar(50) DEFAULT '',
      `zasyp_id` int(11) DEFAULT NULL,
      `wyjasnienie_rozbieznosci` text DEFAULT NULL,
      `uszkodzone_worki` int(11) DEFAULT 0,
      `is_deleted` tinyint(1) DEFAULT 0,
      `deleted_at` datetime DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `start_machine_counter` int(11) DEFAULT 0,
      `sugerowana_folia` varchar(255) DEFAULT '',
      `start_pallet_counter` int(11) DEFAULT 0,
      `data_produkcji` date DEFAULT NULL,
      `opakowanie_id` int(11) DEFAULT NULL,
      `etykieta_id` int(11) DEFAULT NULL,
      `start_checklist_operator_login` varchar(100) DEFAULT NULL,
      `start_checklist_operator_at` datetime DEFAULT NULL,
      `start_checklist_quality_login` varchar(100) DEFAULT NULL,
      `start_checklist_quality_at` datetime DEFAULT NULL,
      `stop_machine_counter` int(11) DEFAULT 0,
      `typ_opakowania` varchar(20) DEFAULT 'worki',
      `ostatnie_wznowienie` datetime DEFAULT NULL,
      `czas_pracy_sekundy` int(11) NOT NULL DEFAULT 0,
      `skan_sscc` varchar(255) DEFAULT NULL,
      `odrzuty_przesiewacz` float DEFAULT 0,
      `rodzaj_palety` varchar(50) DEFAULT 'krajowa',
      `nr_partii` varchar(100) DEFAULT NULL,
      `termin_przydatnosci` varchar(255) DEFAULT NULL,
      `stop_local_counter` int(11) DEFAULT 0,
      PRIMARY KEY (`id`),
      KEY `idx_agro_data` (`data_planu`),
      KEY `idx_agro_sekcja` (`sekcja`),
      KEY `idx_plan_agro_opakowanie` (`opakowanie_id`),
      KEY `idx_plan_agro_etykieta` (`etykieta_id`),
      KEY `idx_plan_agro_data_status_deleted` (`data_planu`,`status`,`is_deleted`),
      KEY `idx_plan_agro_sekcja_data` (`sekcja`,`data_planu`,`status`)
    ) ENGINE=MyISAM AUTO_INCREMENT=117 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `powiadomienia` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `typ` varchar(50) NOT NULL,
      `tytul` varchar(255) NOT NULL,
      `tresc` text NOT NULL,
      `odbiorca_rola` varchar(50) NOT NULL,
      `link_url` varchar(255) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `created_by_user_id` int(11) DEFAULT NULL,
      `is_active` tinyint(1) DEFAULT 1,
      `created_at` datetime DEFAULT current_timestamp(),
      `odbiorca_login` varchar(100) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_powiadomienia_rola_data` (`odbiorca_rola`,`created_at`),
      KEY `idx_powiadomienia_active` (`is_active`,`created_at`),
      KEY `plan_id` (`plan_id`),
      KEY `created_by_user_id` (`created_by_user_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=778 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `powiadomienia_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `typ` varchar(50) NOT NULL,
      `tytul` varchar(255) NOT NULL,
      `tresc` text NOT NULL,
      `odbiorca_rola` varchar(50) NOT NULL,
      `link_url` varchar(255) DEFAULT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `created_by_user_id` int(11) DEFAULT NULL,
      `is_active` tinyint(1) DEFAULT 1,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_powiadomienia_rola_data` (`odbiorca_rola`,`created_at`),
      KEY `idx_powiadomienia_active` (`is_active`,`created_at`),
      KEY `plan_id` (`plan_id`),
      KEY `created_by_user_id` (`created_by_user_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `powiadomienia_odczyty` (
      `notification_id` int(11) NOT NULL,
      `user_id` int(11) NOT NULL,
      `read_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`notification_id`,`user_id`),
      KEY `user_id` (`user_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `powiadomienia_odczyty_agro` (
      `notification_id` int(11) NOT NULL,
      `user_id` int(11) NOT NULL,
      `read_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`notification_id`,`user_id`),
      KEY `user_id` (`user_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `pracownicy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `imie_nazwisko` varchar(255) NOT NULL,
      `grupa` varchar(50) DEFAULT '',
      `urlop_biezacy` int(11) DEFAULT 0,
      `urlop_zalegly` int(11) DEFAULT 0,
      `dzial_id` int(11) DEFAULT NULL,
      `przelozony_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `fk_pracownicy_dzial` (`dzial_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=52 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `print_jobs` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `printer_ip` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `printer_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `zpl_content` text COLLATE utf8mb4_unicode_ci NOT NULL,
      `status` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'PENDING',
      `retry_count` int(11) DEFAULT 0,
      `error_message` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_status` (`status`)
    ) ENGINE=InnoDB AUTO_INCREMENT=29 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `produkcja_inwentaryzacja_sesje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `typ` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'BB_MZ',
      `status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT 'OPEN',
      `created_by` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `comment` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `closed_at` datetime DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_prod_inv_status` (`status`),
      KEY `idx_prod_inv_typ` (`typ`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `produkcja_inwentaryzacja_wpisy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `sesja_id` int(11) NOT NULL,
      `zbiornik` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '',
      `nr_partii` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT '',
      `waga` decimal(12,2) DEFAULT 0.00,
      `komentarz` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `user_login` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `data_wpisu` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_prod_inv_wpisy_zbiornik` (`sesja_id`,`zbiornik`),
      KEY `idx_prod_inv_wpisy_sesja` (`sesja_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `produkty_receptury` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa_produktu` varchar(100) NOT NULL,
      `nr_receptury` varchar(64) DEFAULT '',
      `typ_produkcji` varchar(50) DEFAULT 'worki_zgrzewane_25',
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      `opakowanie_id` int(11) DEFAULT NULL,
      `etykieta_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa_produktu` (`nazwa_produktu`)
    ) ENGINE=MyISAM AUTO_INCREMENT=103 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `przypisania_raportow` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `typ_raportu` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `nazwa_raportu` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `nazwa_drukarki` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '',
      `aktywne` tinyint(1) DEFAULT 0,
      PRIMARY KEY (`id`),
      UNIQUE KEY `typ_raportu` (`typ_raportu`)
    ) ENGINE=MyISAM AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `push_subskrypcje` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `user_id` int(11) NOT NULL,
      `login` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
      `rola` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
      `endpoint` text COLLATE utf8mb4_unicode_ci NOT NULL,
      `p256dh` text COLLATE utf8mb4_unicode_ci NOT NULL,
      `auth` text COLLATE utf8mb4_unicode_ci NOT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `last_used` datetime DEFAULT NULL,
      `is_active` tinyint(1) DEFAULT 1,
      PRIMARY KEY (`id`),
      UNIQUE KEY `unique_endpoint` (`endpoint`(512)) USING HASH,
      KEY `idx_push_user` (`user_id`),
      KEY `idx_push_rola` (`rola`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `raporty` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_raportu` date NOT NULL,
      `stanowisko` varchar(50) NOT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `problem` text DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `raporty_koncowe` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `data_raportu` date NOT NULL,
      `linia` varchar(20) DEFAULT 'PSD',
      `lider_uwagi` text DEFAULT NULL,
      `data_utworzenia` timestamp NOT NULL DEFAULT current_timestamp(),
      `sekcja` varchar(50) DEFAULT NULL,
      `lider_id` int(11) DEFAULT NULL,
      `summary_json` longtext DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `receptury_agro_skladniki` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nr_receptury` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
      `nazwa_produktu` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
      `kolejnosc` int(11) DEFAULT 0,
      `skladnik_nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `ilosc_kg_szarza` float DEFAULT NULL,
      `typ` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'surowiec',
      `aktywny` tinyint(1) DEFAULT 1,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_receptury_agro_nr` (`nr_receptury`),
      KEY `idx_receptury_agro_aktywny` (`aktywny`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `roles` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `name` varchar(50) NOT NULL,
      `label` varchar(100) NOT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `name` (`name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `shift_notes` (
      `id` bigint(20) NOT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `note` text DEFAULT NULL,
      `author` varchar(255) DEFAULT NULL,
      `date` date DEFAULT NULL,
      `created` timestamp NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `shift_notes_agro` (
      `id` bigint(20) NOT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `note` text DEFAULT NULL,
      `author` varchar(255) DEFAULT NULL,
      `date` date DEFAULT NULL,
      `created` timestamp NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `slownik_etykiety_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`) USING HASH
    ) ENGINE=MyISAM AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `slownik_surowcow` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `nazwa` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
      `symbol` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
      `typ` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'surowiec',
      PRIMARY KEY (`id`),
      UNIQUE KEY `nazwa` (`nazwa`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    ;
    CREATE TABLE `szarze` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `waga` float NOT NULL,
      `data_dodania` datetime DEFAULT current_timestamp(),
      `godzina` time DEFAULT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `status` varchar(20) DEFAULT 'zarejestowana',
      `uwagi` text DEFAULT NULL,
      `nr_szarzy` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `plan_id` (`plan_id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=77 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `szarze_agro` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `plan_id` int(11) NOT NULL,
      `waga` float NOT NULL,
      `data_dodania` datetime DEFAULT current_timestamp(),
      `godzina` time DEFAULT NULL,
      `pracownik_id` int(11) DEFAULT NULL,
      `status` varchar(20) DEFAULT 'zarejestowana',
      `nr_szarzy` int(11) DEFAULT NULL,
      `uwagi` text DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`),
      KEY `idx_szarze_agro_plan` (`plan_id`,`data_dodania`)
    ) ENGINE=MyISAM AUTO_INCREMENT=56 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `szarze_parametry` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `szarza_id` int(11) NOT NULL,
      `nazwa` varchar(100) NOT NULL,
      `wartosc` varchar(255) DEFAULT NULL,
      `autor_id` int(11) DEFAULT NULL,
      `data_dodania` timestamp NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `uzytkownicy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `login` varchar(50) NOT NULL,
      `haslo` varchar(255) DEFAULT NULL,
      `rola` varchar(20) NOT NULL,
      `grupa` varchar(50) DEFAULT '',
      `pracownik_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      UNIQUE KEY `login` (`login`)
    ) ENGINE=MyISAM AUTO_INCREMENT=66 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `wnioski_wolne` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `pracownik_id` int(11) NOT NULL,
      `typ` varchar(50) NOT NULL,
      `data_od` date NOT NULL,
      `data_do` date NOT NULL,
      `czas_od` time DEFAULT NULL,
      `czas_do` time DEFAULT NULL,
      `powod` text DEFAULT NULL,
      `status` varchar(20) DEFAULT 'pending',
      `zlozono` datetime DEFAULT current_timestamp(),
      `decyzja_dnia` datetime DEFAULT NULL,
      `lider_id` int(11) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `pracownik_id` (`pracownik_id`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_dosypka_added_events` (
      `id` bigint(20) NOT NULL AUTO_INCREMENT,
      `linia` varchar(16) NOT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `produkt` varchar(255) DEFAULT NULL,
      `szarza_nr` int(11) DEFAULT NULL,
      `dosypki_count` int(11) DEFAULT NULL,
      `event_timestamp` double NOT NULL,
      `audio_filename` varchar(255) DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_zasyp_dosypka_added_events_linia_ts` (`linia`,`event_timestamp`)
    ) ENGINE=InnoDB AUTO_INCREMENT=76 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_etap_start_events` (
      `id` bigint(20) NOT NULL AUTO_INCREMENT,
      `linia` varchar(16) NOT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `produkt` varchar(255) DEFAULT NULL,
      `szarza_nr` int(11) DEFAULT NULL,
      `event_timestamp` double NOT NULL,
      `audio_filename` varchar(255) DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_zasyp_start_events_linia_ts` (`linia`,`event_timestamp`)
    ) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_etapy` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(10) NOT NULL,
      `plan_id` int(11) NOT NULL,
      `data_planu` date NOT NULL,
      `szarza_nr` int(11) NOT NULL DEFAULT 1,
      `etap` tinyint(4) NOT NULL,
      `czas_start` datetime DEFAULT NULL,
      `czas_stop` datetime DEFAULT NULL,
      `start_login` varchar(100) DEFAULT NULL,
      `stop_login` varchar(100) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_zasyp_etapy_linia_plan_szarza_etap` (`linia`,`plan_id`,`szarza_nr`,`etap`),
      UNIQUE KEY `uq_zasyp_etapy_linia_plan_etap` (`linia`,`plan_id`,`szarza_nr`,`etap`),
      KEY `idx_zasyp_etapy_linia_data` (`linia`,`data_planu`),
      KEY `idx_zasyp_etapy_linia_plan` (`linia`,`plan_id`),
      KEY `idx_zasyp_etapy_linia_plan_szarza` (`linia`,`plan_id`,`szarza_nr`)
    ) ENGINE=MyISAM AUTO_INCREMENT=171 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_etapy_parametry` (
      `id` int(11) NOT NULL AUTO_INCREMENT,
      `linia` varchar(10) NOT NULL,
      `plan_id` int(11) NOT NULL,
      `data_planu` date NOT NULL,
      `wielkosc_szarzy_kg` float DEFAULT NULL,
      `updated_by_login` varchar(100) DEFAULT NULL,
      `created_at` datetime DEFAULT current_timestamp(),
      `updated_at` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`id`),
      UNIQUE KEY `uq_zasyp_etapy_param_linia_plan` (`linia`,`plan_id`),
      KEY `idx_zasyp_etapy_param_linia_data` (`linia`,`data_planu`),
      KEY `idx_zasyp_etapy_param_linia_plan` (`linia`,`plan_id`)
    ) ENGINE=MyISAM AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_mieszanie_start_events` (
      `id` bigint(20) NOT NULL AUTO_INCREMENT,
      `linia` varchar(16) NOT NULL,
      `plan_id` int(11) DEFAULT NULL,
      `etap_nr` int(11) DEFAULT NULL,
      `produkt` varchar(255) DEFAULT NULL,
      `szarza_nr` int(11) DEFAULT NULL,
      `event_timestamp` double NOT NULL,
      `audio_filename` varchar(255) DEFAULT NULL,
      `created_at` datetime NOT NULL DEFAULT current_timestamp(),
      PRIMARY KEY (`id`),
      KEY `idx_zasyp_mieszanie_start_events_linia_ts` (`linia`,`event_timestamp`)
    ) ENGINE=InnoDB AUTO_INCREMENT=105 DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_zwolnienia_ack` (
      `linia` varchar(16) NOT NULL,
      `timestamp_unix` double NOT NULL,
      `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`linia`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE TABLE `zasyp_zwolnienia_mieszalnika` (
      `linia` varchar(16) NOT NULL,
      `timestamp_unix` double NOT NULL,
      `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
      PRIMARY KEY (`linia`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ;
    CREATE ALGORITHM=UNDEFINED DEFINER=`biblioteka`@`%` SQL SECURITY DEFINER VIEW `zasypy` AS select `szarze`.`id` AS `id`,`szarze`.`plan_id` AS `plan_id`,`szarze`.`waga` AS `waga`,`szarze`.`data_dodania` AS `data_dodania`,`szarze`.`godzina` AS `godzina`,`szarze`.`pracownik_id` AS `pracownik_id`,`szarze`.`status` AS `status`,`szarze`.`uwagi` AS `uwagi`,`szarze`.`nr_szarzy` AS `nr_szarzy`,`szarze`.`nr_szarzy` AS `nr_zasypu` from `szarze`
    ;
    CREATE ALGORITHM=UNDEFINED DEFINER=`biblioteka`@`%` SQL SECURITY DEFINER VIEW `zasypy_agro` AS select `szarze_agro`.`id` AS `id`,`szarze_agro`.`plan_id` AS `plan_id`,`szarze_agro`.`waga` AS `waga`,`szarze_agro`.`data_dodania` AS `data_dodania`,`szarze_agro`.`godzina` AS `godzina`,`szarze_agro`.`pracownik_id` AS `pracownik_id`,`szarze_agro`.`status` AS `status`,`szarze_agro`.`uwagi` AS `uwagi`,`szarze_agro`.`nr_szarzy` AS `nr_szarzy`,`szarze_agro`.`nr_szarzy` AS `nr_zasypu` from `szarze_agro`
    ;
    CREATE TABLE `zgloszenia_bledow` (
      `id` bigint(20) NOT NULL,
      `timestamp` datetime DEFAULT current_timestamp(),
      `login` varchar(50) NOT NULL,
      `opis` text NOT NULL,
      `sciezka` varchar(255) DEFAULT NULL,
      `zalaczniki` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`zalaczniki`)),
      `status` varchar(30) DEFAULT 'nowy',
      `odpowiedz_admina` text DEFAULT NULL,
      `odpowiedz_timestamp` datetime DEFAULT NULL,
      `odpowiedz_by_login` varchar(50) DEFAULT NULL,
      PRIMARY KEY (`id`),
      KEY `idx_zgloszenia_login` (`login`),
      KEY `idx_zgloszenia_status` (`status`)
    ) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4
    ;
    
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
