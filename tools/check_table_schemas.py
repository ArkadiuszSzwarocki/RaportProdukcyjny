import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv(override=True)

host = os.getenv('DB_HOST', 'raportprodukcji.mycloudnas.com')
port = int(os.getenv('DB_PORT', 3307))
user = os.getenv('DB_USER', 'biblioteka')
password = os.getenv('DB_PASSWORD', 'Filipinka2025')

tables_to_check = [
    'plan_produkcji',
    'plan_produkcji_agro',
    'szarze',
    'szarze_agro',
    'palety_workowanie',
    'palety_agro',
    'magazyn_palety',
    'magazyn_palety_agro',
    'bufor',
    'bufor_agro',
    'dosypki',
    'dosypki_agro',
    'zasyp_etapy',
    'zasyp_etapy_parametry',
    'mom_rozliczenia',
    'mom_pozycje',
    'agro_workowanie_rozliczenie',
    'palety_historia'
]

def main():
    conn_src = mysql.connector.connect(host=host, port=port, user=user, password=password, database='biblioteka_testowa')
    conn_dest = mysql.connector.connect(host=host, port=port, user=user, password=password, database='biblioteka')
    
    cursor_src = conn_src.cursor(dictionary=True)
    cursor_dest = conn_dest.cursor(dictionary=True)
    
    print("Checking schemas of tables in source vs destination:")
    for table in tables_to_check:
        print(f"\n--- Table: {table} ---")
        
        # Check source
        cursor_src.execute(f"SHOW TABLES LIKE '{table}'")
        src_exists = cursor_src.fetchone() is not None
        
        # Check destination
        cursor_dest.execute(f"SHOW TABLES LIKE '{table}'")
        dest_exists = cursor_dest.fetchone() is not None
        
        print(f"Exists in Source (testowa): {src_exists}, Exists in Dest (prod): {dest_exists}")
        
        if not src_exists or not dest_exists:
            continue
            
        # Get source columns
        cursor_src.execute(f"SHOW COLUMNS FROM {table}")
        src_cols = {r['Field']: r for r in cursor_src.fetchall()}
        
        # Get dest columns
        cursor_dest.execute(f"SHOW COLUMNS FROM {table}")
        dest_cols = {r['Field']: r for r in cursor_dest.fetchall()}
        
        src_only = set(src_cols.keys()) - set(dest_cols.keys())
        dest_only = set(dest_cols.keys()) - set(src_cols.keys())
        common = set(src_cols.keys()) & set(dest_cols.keys())
        
        if src_only:
            print(f"  Only in Source (testowa): {list(src_only)}")
        if dest_only:
            print(f"  Only in Dest (prod): {list(dest_only)}")
        print(f"  Common columns count: {len(common)}")
        
    cursor_src.close()
    cursor_dest.close()
    conn_src.close()
    conn_dest.close()

if __name__ == '__main__':
    main()
