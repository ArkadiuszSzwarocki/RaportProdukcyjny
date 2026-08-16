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

def full_clone():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS
        )
        cursor = conn.cursor()
        
        # Pobierz wszystkie tabele i widoki
        cursor.execute(f"SHOW FULL TABLES FROM {SOURCE_DB}")
        tables = cursor.fetchall()
        
        print(f"[*] Rozpoczynanie klonowania {len(tables)} obiektów...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        for table_name, table_type in tables:
            if table_type == 'BASE TABLE':
                # Klonuj strukturę tabeli
                cursor.execute(f"DROP TABLE IF EXISTS {TARGET_DB}.{table_name}")
                cursor.execute(f"CREATE TABLE {TARGET_DB}.{table_name} LIKE {SOURCE_DB}.{table_name}")
                
                # Jeśli to jedna z kluczowych tabel, skopiuj też dane
                if table_name in ['uzytkownicy', 'pracownicy', 'magazyn_surowce', 'magazyn_opakowania', 'produkty_receptury', 'agro_stanowiska']:
                    cursor.execute(f"INSERT INTO {TARGET_DB}.{table_name} SELECT * FROM {SOURCE_DB}.{table_name}")
                    print(f"  [OK] Tabela + Dane: {table_name}")
                else:
                    print(f"  [OK] Struktura: {table_name}")
            
            elif table_type == 'VIEW':
                # Klonuj widok (pobierz definicję i stwórz w docelowej)
                cursor.execute(f"SHOW CREATE VIEW {SOURCE_DB}.{table_name}")
                view_def = cursor.fetchone()[1]
                # Podmień nazwę bazy w definicji widoku jeśli jest zahardkodowana
                view_def = view_def.replace(f"`{SOURCE_DB}`.", f"`{TARGET_DB}`.")
                
                cursor.execute(f"DROP VIEW IF EXISTS {TARGET_DB}.{table_name}")
                cursor.execute(view_def)
                print(f"  [OK] Widok: {table_name}")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print("\n[SUKCES] Baza testowa jest teraz pełnym odbiciem produkcji.")
        
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n[BŁĄD]: {e}")

if __name__ == "__main__":
    full_clone()
