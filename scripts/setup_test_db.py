"""
Skrypt do przygotowania lokalnej testowej bazy danych.
Klonuje strukturę z 'biblioteka' do 'biblioteka_testowa'.
"""
import mysql.connector
import os
from dotenv import load_dotenv

# Wczytaj konfigurację z .env
load_dotenv(override=True)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3307))
DB_USER = os.getenv('DB_USER', 'biblioteka')
DB_PASS = os.getenv('DB_PASSWORD', '')
SOURCE_DB = 'biblioteka'
TARGET_DB = 'biblioteka_testowa'

def setup_test_db():
    try:
        # 1. Połącz się bez wybierania konkretnej bazy
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS
        )
        cursor = conn.cursor()

        print(f"[*] Łączenie z serwerem {DB_HOST}:{DB_PORT}...")

        # 2. Stwórz bazę testową jeśli nie istnieje
        print(f"[*] Tworzenie bazy {TARGET_DB} (jeśli nie istnieje)...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {TARGET_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

        # 3. Pobierz listę tabel z produkcji
        print(f"[*] Pobieranie listy tabel z {SOURCE_DB}...")
        cursor.execute(f"SHOW TABLES FROM {SOURCE_DB}")
        tables = [row[0] for row in cursor.fetchall()]

        # 4. Kopiuj strukturę tabel (bez danych, aby baza była czysta)
        print(f"[*] Kopiowanie struktury {len(tables)} tabel...")
        for table in tables:
            # Pomiń widoki (VIEWS) - one zostaną utworzone przez db.setup_database() w aplikacji
            cursor.execute(f"SHOW FULL TABLES FROM {SOURCE_DB} LIKE '{table}'")
            if cursor.fetchone()[1] == 'VIEW':
                continue
                
            cursor.execute(f"CREATE TABLE IF NOT EXISTS {TARGET_DB}.{table} LIKE {SOURCE_DB}.{table}")
        
        print(f"[OK] Baza {TARGET_DB} jest gotowa do pracy!")
        print(f"[!] Upewnij się, że w pliku .env masz: DB_NAME={TARGET_DB}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[BŁĄD] Nie udało się przygotować bazy: {e}")

if __name__ == "__main__":
    setup_test_db()
