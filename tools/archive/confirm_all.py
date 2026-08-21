import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.db import get_db_connection

def confirm_all():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Confirm all magazyn_ruch
        for suffix in ['agro', 'psd', 'pelet', 'linia2']:
            try:
                table = f"magazyn_ruch_{suffix}"
                cursor.execute(f"UPDATE {table} SET status = 'POTWIERDZONE' WHERE status = 'OCZEKUJE'")
                print(f"Updated {cursor.rowcount} rows in {table}")
            except Exception as e:
                pass
                
        # 2. Confirm magazyn_dostawy
        cursor.execute("SELECT id, items FROM magazyn_dostawy WHERE status != 'COMPLETED'")
        rows = cursor.fetchall()
        for row in rows:
            try:
                items = json.loads(row[1]) if row[1] else []
                changed = False
                for item in items:
                    if not item.get('accepted') and not item.get('rejected'):
                        item['accepted'] = True
                        item['accepted_by'] = 'System'
                        changed = True
                if changed:
                    cursor.execute("UPDATE magazyn_dostawy SET items = %s, status = 'COMPLETED', potwierdzone_at = NOW() WHERE id = %s", (json.dumps(items), row[0]))
            except Exception as e:
                pass
        
        # 3. Zakończ wszystkie plany w toku? No, they probably mean warehouse movements.
        # "pozamykaj potwierdz co nie potwierdzone"
        
        conn.commit()
        print("Done confirming pending items.")
    finally:
        conn.close()

if __name__ == '__main__':
    confirm_all()
