
import mysql.connector
from app.config import DB_CONFIG

def check_diff():
    try:
        config = DB_CONFIG.copy()
        config.pop('database', None)
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        tables = ['magazyn_surowce', 'magazyn_opakowania', 'plan_produkcji', 'plan_produkcji_agro']
        
        for t in tables:
            print(f"\n--- TABLE: {t} ---")
            
            conn.database = 'biblioteka'
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            c1 = cursor.fetchone()[0]
            
            conn.database = 'biblioteka_testowa'
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            c2 = cursor.fetchone()[0]
            
            print(f"  biblioteka: {c1} rows")
            print(f"  biblioteka_testowa: {c2} rows")
            
            if t.startswith('magazyn'):
                conn.database = 'biblioteka'
                cursor.execute(f"SELECT id, nazwa, nr_palety, stan_magazynowy FROM {t} ORDER BY id DESC LIMIT 1")
                r1 = cursor.fetchone()
                
                conn.database = 'biblioteka_testowa'
                cursor.execute(f"SELECT id, nazwa, nr_palety, stan_magazynowy FROM {t} ORDER BY id DESC LIMIT 1")
                r2 = cursor.fetchone()
                
                print(f"  Latest in biblioteka: {r1}")
                print(f"  Latest in biblioteka_testowa: {r2}")
            else:
                conn.database = 'biblioteka'
                cursor.execute(f"SELECT id, produkt, data_planu, status FROM {t} ORDER BY id DESC LIMIT 1")
                r1 = cursor.fetchone()
                
                conn.database = 'biblioteka_testowa'
                cursor.execute(f"SELECT id, produkt, data_planu, status FROM {t} ORDER BY id DESC LIMIT 1")
                r2 = cursor.fetchone()
                
                print(f"  Latest in biblioteka: {r1}")
                print(f"  Latest in biblioteka_testowa: {r2}")
                    
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_diff()
