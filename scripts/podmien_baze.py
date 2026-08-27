#!/usr/bin/env python3
"""
SKRYPT: podmien_baze.py
OPIS: Narzędzie Python do automatycznej podmiany bazy danych MySQL w środowisku Docker.
PROJEKT: Raport Produkcyjny
ŚRODOWISKO: Serwer Ubuntu (Localhost)
"""

import argparse
import os
import subprocess
import sys
import time

DB_PASS = "VVezyr$$"
DB_NAME = "biblioteka"
DEFAULT_SQL_FILE = "nowa_baza.sql"

def run_cmd(cmd, check=True, shell=True):
    print(f"\n[EXEC] {cmd}")
    res = subprocess.run(cmd, shell=shell, check=check)
    return res.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Automatyczna procedura podmiany bazy danych (Docker / Python)")
    parser.add_argument("sql_file", nargs="?", default=DEFAULT_SQL_FILE, help="Nazwa/ścieżka pliku zrzutu bazy SQL (domyślnie: nowa_baza.sql)")
    parser.add_argument("--yes", "-y", action="store_true", help="Automatyczne potwierdzenie (bez pytania t/n)")
    args = parser.parse_args()

    sql_file = args.sql_file

    print("======================================================================")
    print("    PROCEDURA PODMIANY BAZY DANYCH (ŚRODOWISKO DOCKER)")
    print("    Projekt: Raport Produkcyjny | Środowisko: Serwer Ubuntu (Localhost)")
    print("======================================================================\n")

    # KROK 1: Przygotowanie pliku
    print("--- KROK 1: Przygotowanie pliku ---")
    if not os.path.isfile(sql_file):
        print(f"❌ [BŁĄD] Plik '{sql_file}' nie został znaleziony w katalogu ({os.getcwd()})!")
        print("Upewnij się, że nowy zrzut bazy z QNAP-a (np. nowa_baza.sql) znajduje się w Twoim głównym katalogu projektu na Ubuntu:")
        print("  ~/raportprodukcyjny")
        sql_files = [f for f in os.listdir(".") if f.endswith(".sql")]
        if sql_files:
            print(f"Znalezione pliki .sql w bieżącym katalogu: {', '.join(sql_files)}")
        else:
            print("Brak plików .sql w tym katalogu.")
        sys.exit(1)

    file_size_mb = os.path.getsize(sql_file) / (1024 * 1024)
    print(f"✅ Znaleziono plik bazy danych: {sql_file} ({file_size_mb:.2f} MB)")

    if not args.yes:
        confirm = input(f"\n⚠️ Czy na pewno chcesz usunąć stary wolumen bazy i wgrać '{sql_file}'? (t/N): ")
        if confirm.strip().lower() not in ['t', 'tak', 'y', 'yes']:
            print("🚫 Anulowano procedurę podmiany bazy.")
            sys.exit(0)

    # KROK 2: Czyszczenie starego środowiska
    print("\n--- KROK 2: Czyszczenie starego środowiska ---")
    print("Zatrzymywanie kontenerów i usuwanie starego wolumenu bazy danych...")
    run_cmd("sudo docker-compose down -v")

    # KROK 3: Uruchomienie czystej bazy danych
    print("\n--- KROK 3: Uruchomienie czystej bazy danych ---")
    print("Podnoszenie kontenera bazy danych...")
    run_cmd("sudo docker-compose up -d db")

    print("Oczekiwanie około 15-20 sekund na pełne uruchomienie i inicjalizację MySQL...")
    for i in range(20, 0, -1):
        print(f"Inicjalizacja MySQL... pozostało {i}s \r", end="", flush=True)
        time.sleep(1)
    print("\n✅ Kontener db wystartował.")

    # KROK 4: Import nowych danych
    print("\n--- KROK 4: Import nowych danych ---")
    print(f"Tworzenie czystej struktury bazy o nazwie '{DB_NAME}'...")
    run_cmd(f"sudo docker-compose exec -T db mysql -u root -p'{DB_PASS}' -e \"CREATE DATABASE IF NOT EXISTS {DB_NAME};\"")
    print(f"Wgrywanie pliku '{sql_file}' do bazy '{DB_NAME}'...")
    run_cmd(f"sudo docker-compose exec -T db mysql -u root -p'{DB_PASS}' {DB_NAME} < \"{sql_file}\"")
    print(f"✅ Pomyślnie zaimportowano plik '{sql_file}' do bazy '{DB_NAME}'!")

    # KROK 5: Uruchomienie aplikacji
    print("\n--- KROK 5: Uruchomienie aplikacji ---")
    print("Gdy import zakończy się bez błędów, uruchamianie kontenera z aplikacją...")
    run_cmd("sudo docker-compose up -d app")

    # KROK 6: Weryfikacja
    print("\n======================================================================")
    print(" 🎉 PROCEDURA PODMIANY BAZY DANYCH ZAKOŃCZONA SUKCESEM!")
    print("======================================================================")
    print("KROK 6: Weryfikacja")
    print("Wejdź do przeglądarki pod adres: https://localhost:5005")
    print("Zaloguj się i sprawdź, czy nowe dane są widoczne. Procedura zakończona!\n")

if __name__ == "__main__":
    main()
