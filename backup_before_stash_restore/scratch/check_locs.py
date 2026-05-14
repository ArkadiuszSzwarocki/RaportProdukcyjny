from app.db import get_db_connection

def check_locations():
    try:
        conn = get_db_connection()
        curr = conn.cursor()
        curr.execute('SELECT DISTINCT lokalizacja FROM magazyn_surowce WHERE lokalizacja LIKE "%PODŁOGA%"')
        rows = curr.fetchall()
        print("Surowce:", rows)
        
        curr.execute('SELECT DISTINCT lokalizacja FROM magazyn_opakowania WHERE lokalizacja LIKE "%PODŁOGA%"')
        rows = curr.fetchall()
        print("Opakowania:", rows)
        
        curr.execute('SELECT DISTINCT lokalizacja FROM magazyn_palety WHERE lokalizacja LIKE "%PODŁOGA%"')
        rows = curr.fetchall()
        print("Palety PSD:", rows)

        curr.execute('SELECT DISTINCT lokalizacja FROM magazyn_palety_agro WHERE lokalizacja LIKE "%PODŁOGA%"')
        rows = curr.fetchall()
        print("Palety Agro:", rows)
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_locations()
