import sys
import json
from datetime import date, datetime, timedelta
from app.db import get_db_connection

def default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return str(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def main():
    conn = get_db_connection()
    if not conn:
        print("Brak połączenia z bazą.")
        sys.exit(1)
    
    cursor = conn.cursor(dictionary=True)
    
    # Get plan_history
    cursor.execute("SELECT * FROM plan_history WHERE plan_id IN (1216, 1224) ORDER BY created_at")
    history = cursor.fetchall()
    
    # Get palety_workowanie
    cursor.execute("SELECT * FROM palety_workowanie WHERE plan_id IN (1216, 1224) ORDER BY data_dodania")
    palety = cursor.fetchall()
    
    data = {
        "history": history,
        "palety": palety
    }
    
    with open('tmp_workowanie_details.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, default=default_serializer, indent=4)
        print("Zapisano logi do tmp_workowanie_details.json")
        
    conn.close()

if __name__ == '__main__':
    main()
