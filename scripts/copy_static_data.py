"""
Skrypt do kopiowania podstawowych danych (użytkownicy, pracownicy, surowce)
z bazy produkcyjnej do testowej.
"""
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3307))
DB_USER = os.getenv('DB_USER', 'biblioteka')
DB_PASS = os.getenv('DB_PASSWORD', '')
SOURCE_DB = 'biblioteka'
TARGET_DB = 'biblioteka_testowa'

# Tabele, które chcemy sklonować (sama zawartość)
STATIC_TABLES = [
    'uzytkownicy',
    'pracownicy',
    'magazyn_surowce',
    'magazyn_opakowania',
    'produkty_receptury',
    'agro_stanowiska'
]

def copy_data():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS
        )
        cursor = conn.cursor()
        
        print(f"[*] Rozpoczynanie kopiowania danych z {SOURCE_DB} do {TARGET_DB}...")

        # Wyłączamy sprawdzanie kluczy obcych na czas kopiowania
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        for table in STATIC_TABLES:
            print(f"[*] Kopiowanie tabeli: {table}...", end=" ", flush=True)
            
            # 1. Czyścimy tabelę docelową
            cursor.execute(f"TRUNCATE TABLE {TARGET_DB}.{table}")
            
            # 2. Kopiujemy dane (INSERT INTO ... SELECT * FROM ...)
            cursor.execute(f"INSERT INTO {TARGET_DB}.{table} SELECT * FROM {SOURCE_DB}.{table}")
            
            print("GOTOWE")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        
        print(f"\n[OK] Dane zostały pomyślnie skopiowane!")
        print(f"[!] Możesz teraz zalogować się do wersji testowej swoimi normalnymi danymi z produkcji.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n[BŁĄD] Podczas kopiowania danych: {e}")

if __name__ == "__main__":
    copy_data()
