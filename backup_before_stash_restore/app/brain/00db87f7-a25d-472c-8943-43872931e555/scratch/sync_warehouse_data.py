
import mysql.connector
from app.config import DB_CONFIG

def sync_data():
    try:
        # Połączenie do serwera (używamy DB_CONFIG jako bazy, ale będziemy skakać między bazami)
        config = DB_CONFIG.copy()
        config.pop('database', None)
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        tables_to_sync = [
            'magazyn_surowce',
            'magazyn_opakowania',
            'magazyn_dodatki',
            'magazyn_dostawy',
            'magazyn_pojemnosci',
            'magazyn_ruch',
            'magazyn_agro_ruch',
            'magazyn_archiwum',
            'magazyn_agro_slownik_surowce'
        ]
        
        for table in tables_to_sync:
            print(f"Synchronizing table: {table}...")
            
            # 1. Pobierz dane z biblioteka
            conn.database = 'biblioteka'
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            
            if not rows:
                print(f"  No data in source table {table}. Skipping.")
                continue
                
            # 2. Wyczyść i wstaw do biblioteka_testowa
            conn.database = 'biblioteka_testowa'
            cursor.execute(f"DELETE FROM {table}") # Truncate/Delete before sync
            
            if rows:
                columns = rows[0].keys()
                placeholders = ", ".join(["%s"] * len(columns))
                sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                
                values = [tuple(row[col] for col in columns) for row in rows]
                cursor.executemany(sql, values)
                print(f"  Inserted {len(values)} rows into {table}.")
            
            conn.commit()
            
        conn.close()
        print("\nSynchronization completed successfully.")
    except Exception as e:
        print(f"Error during synchronization: {e}")

if __name__ == "__main__":
    sync_data()
