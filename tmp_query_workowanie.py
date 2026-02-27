import sys
import json
from datetime import date, datetime
from app.db import get_db_connection

def default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def main():
    conn = get_db_connection()
    if not conn:
        print("Brak połączenia z bazą.")
        sys.exit(1)
    
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT id, data_planu, sekcja, produkt, tonaz, status, real_start, real_stop, kolejnosc 
    FROM plan_produkcji 
    WHERE data_planu = '2026-02-27' AND sekcja = 'workowanie'
    ORDER BY id
    """
    cursor.execute(query)
    results = cursor.fetchall()
    
    with open('tmp_workowanie_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, default=default_serializer, indent=4)
        print("Zapisano wyniki do tmp_workowanie_results.json")
        
    conn.close()

if __name__ == '__main__':
    main()
