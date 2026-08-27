"""
Skrypt migracyjny konwertujący wszystkie tabele w bazie danych z silnika MyISAM na InnoDB.
"""
import os
import sys
import time

# Zapewnij dostępność modułu app w ścieżce wyszukiwania Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import get_db_connection

def migrate_tables_to_innodb():
    print("=== Rozpoczynanie migracji tabel MyISAM do InnoDB ===")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Pobierz wszystkie tabele korzystające z silnika MyISAM w obecnej bazie
        cursor.execute("""
            SELECT TABLE_NAME, TABLE_ROWS 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE() AND UPPER(ENGINE) = 'MYISAM'
            ORDER BY TABLE_NAME ASC
        """)
        myisam_tables = cursor.fetchall()
        
        total_tables = len(myisam_tables)
        print(f"Znaleziono {total_tables} tabel z silnikiem MyISAM do przekonwertowania.")
        
        if total_tables == 0:
            print("Wszystkie tabele w bazie korzystają już z silnika InnoDB lub innego.")
            return
        
        success_count = 0
        error_count = 0
        
        start_total = time.time()
        
        for idx, t in enumerate(myisam_tables, 1):
            table_name = t['TABLE_NAME']
            table_rows = t['TABLE_ROWS'] or 0
            
            print(f"[{idx}/{total_tables}] Konwersja tabeli `{table_name}` ({table_rows} wierszy)...", end="", flush=True)
            start_table = time.time()
            
            try:
                cursor.execute(f"ALTER TABLE `{table_name}` ENGINE=InnoDB")
                conn.commit()
                elapsed = time.time() - start_table
                print(f" OK ({elapsed:.2f}s)")
                success_count += 1
            except Exception as e:
                elapsed = time.time() - start_table
                print(f" BŁĄD ({elapsed:.2f}s): {e}")
                error_count += 1
                
        total_time = time.time() - start_total
        print("\n=== Podsumowanie migracji ===")
        print(f"Pomyślnie przekonwertowano: {success_count}/{total_tables}")
        print(f"Błędy: {error_count}")
        print(f"Całkowity czas: {total_time:.2f}s")
        
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    migrate_tables_to_innodb()
