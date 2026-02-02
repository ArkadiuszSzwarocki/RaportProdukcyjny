from db import get_db_connection
from datetime import date
import time

data_dzisiaj = str(date.today())

def check_buffer():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, tonaz_rzeczywisty, status
        FROM plan_produkcji 
        WHERE data_planu=%s AND sekcja='Workowanie' AND produkt='test'
        ORDER BY id
    """, (data_dzisiaj,))
    
    result = {}
    for row in cursor.fetchall():
        plan_id, tonaz_rz, status = row
        result[plan_id] = (tonaz_rz, status)
    conn.close()
    return result

print("\nSTAN PRZED:")
before = check_buffer()
for plan_id in sorted(before.keys()):
    tonaz_rz, status = before[plan_id]
    print(f"  ID={plan_id} | Status={status:12s} | Realizacja={tonaz_rz:6.0f}")

print("\n⏳ Czekaj 2 sekundy...")
time.sleep(2)

print("\nSTAN PO:")
after = check_buffer()
for plan_id in sorted(after.keys()):
    tonaz_rz, status = after[plan_id]
    if plan_id in before:
        przed = before[plan_id][0]
        zmiana = tonaz_rz - przed
        if zmiana != 0:
            print(f"  ID={plan_id} | Status={status:12s} | Realizacja={tonaz_rz:6.0f} ({zmiana:+.0f}) ✓")
        else:
            print(f"  ID={plan_id} | Status={status:12s} | Realizacja={tonaz_rz:6.0f}")
    else:
        print(f"  ID={plan_id} | Status={status:12s} | Realizacja={tonaz_rz:6.0f} (NOWY!)")
