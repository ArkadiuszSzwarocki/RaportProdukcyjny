
import mysql.connector
from app.config import DB_CONFIG

def normalize_hydro():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    tables_to_update = [
        ('magazyn_surowce', 'nazwa'),
        ('magazyn_ruch', 'surowiec_nazwa'),
        ('magazyn_agro_ruch', 'surowiec_nazwa')
    ]
    
    print("Starting normalization of 'Hydro' nomenclature...")
    
    for table, column in tables_to_update:
        # Update variants to 'Hydro'
        query = f"UPDATE {table} SET {column} = 'Hydro' WHERE {column} LIKE 'Hydro %' OR {column} = 'hydr' OR {column} = 'hydro'"
        cursor.execute(query)
        print(f"Updated {cursor.rowcount} rows in {table}.")
        
    conn.commit()
    conn.close()
    print("Normalization complete.")

if __name__ == "__main__":
    normalize_hydro()
