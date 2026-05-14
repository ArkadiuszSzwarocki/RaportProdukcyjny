from app.db import get_db_connection
import json

def check_hydro():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check variations in inventory
    cursor.execute("SELECT DISTINCT nazwa FROM magazyn_surowce WHERE nazwa LIKE '%hyd%' OR nazwa LIKE '%Hydro%'")
    inventory_variations = cursor.fetchall()
    
    # Check variations in dictionary
    cursor.execute("SELECT id, nazwa FROM magazyn_agro_slownik_surowce WHERE nazwa LIKE '%hyd%' OR nazwa LIKE '%Hydro%'")
    dictionary_variations = cursor.fetchall()
    
    # Check deliveries
    cursor.execute("SELECT DISTINCT surowiec_nazwa FROM magazyn_ruch WHERE surowiec_nazwa LIKE '%hyd%' OR surowiec_nazwa LIKE '%Hydro%'")
    delivery_variations = cursor.fetchall()
    
    print("--- INVENTORY ---")
    print(json.dumps(inventory_variations, indent=2))
    print("--- DICTIONARY ---")
    print(json.dumps(dictionary_variations, indent=2))
    print("--- DELIVERIES ---")
    print(json.dumps(delivery_variations, indent=2))
    
    conn.close()

if __name__ == "__main__":
    check_hydro()
