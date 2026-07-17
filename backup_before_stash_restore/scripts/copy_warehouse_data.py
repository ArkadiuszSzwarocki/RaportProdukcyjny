import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3307))
DB_USER = os.getenv('DB_USER', 'biblioteka')
DB_PASS = os.getenv('DB_PASSWORD', '')

SRC_DB = 'biblioteka'
DST_DB = 'biblioteka_testowa'

TABLES_TO_COPY = [
    'magazyn_surowce',
    'magazyn_opakowania',
    'magazyn_agro_slownik_surowce',
    'magazyn_palety',
    'magazyn_palety_agro',
    'produkty_receptury'
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

        print(f"[*] Rozpoczynam kopiowanie danych magazynowych z {SRC_DB} do {DST_DB}...")

        # Wyłącz klucze obce na czas kopiowania
        cursor.execute(f"USE {DST_DB}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        for table in TABLES_TO_COPY:
            print(f"    -> Kopiowanie tabeli: {table}...")
            
            # Wyczyść tabelę docelową
            cursor.execute(f"TRUNCATE TABLE {DST_DB}.{table}")
            
            # Pobierz kolumny (żeby uniknąć problemów z różnicami w schema jeśli jakieś są)
            cursor.execute(f"SHOW COLUMNS FROM {SRC_DB}.{table}")
            columns = [row[0] for row in cursor.fetchall()]
            col_str = ", ".join(columns)
            
            # Kopiuj dane
            sql = f"INSERT INTO {DST_DB}.{table} ({col_str}) SELECT {col_str} FROM {SRC_DB}.{table}"
            cursor.execute(sql)
            
            print(f"       [OK] Skopiowano {cursor.rowcount} rekordów.")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print("[DONE] Dane magazynowe zostały pomyślnie zsynchronizowane.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[BŁĄD]: {e}")

if __name__ == "__main__":
    copy_data()
