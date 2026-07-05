import os
import sys

# Upewnij się, że główny katalog aplikacji jest w ścieżce
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.db import get_db_connection

def add_indexes():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        tables = [
            'magazyn_surowce',
            'magazyn_opakowania',
            'magazyn_palety',
            'magazyn_palety_agro'
        ]
        
        for table in tables:
            print(f"Adding indexes for {table}...")
            # index on lokalizacja
            try:
                cursor.execute(f"CREATE INDEX idx_lokalizacja ON {table} (lokalizacja)")
                print(f"  - index on lokalizacja added")
            except Exception as e:
                print(f"  - idx_lokalizacja: {e}")
                
            # index on nr_palety
            try:
                cursor.execute(f"CREATE INDEX idx_nr_palety ON {table} (nr_palety)")
                print(f"  - index on nr_palety added")
            except Exception as e:
                print(f"  - idx_nr_palety: {e}")

            # index on data_przydatnosci
            try:
                cursor.execute(f"CREATE INDEX idx_data_przydatnosci ON {table} (data_przydatnosci)")
                print(f"  - index on data_przydatnosci added")
            except Exception as e:
                print(f"  - idx_data_przydatnosci: {e}")
                
        conn.commit()
        print("Done.")
    except Exception as e:
        print(f"Fatal Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    add_indexes()
