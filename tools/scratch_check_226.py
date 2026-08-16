import os
import sys

sys.path.insert(0, os.getcwd())
from app.core.database import get_db_connection
from app.utils.pallet_label import prepare_pallet_label_data

try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM palety_agro WHERE plan_id = 226 ORDER BY id DESC LIMIT 1")
    pw = cur.fetchone()
    if pw:
        lbl = prepare_pallet_label_data(cur, pw['id'], linia='AGRO', source_table='workowanie')
        print("LABEL DATA FROM WORKOWANIE:")
        print(lbl)
    else:
        print("No pallet in palety_agro for plan 226")
        
    cur.execute("SELECT id FROM magazyn_palety_agro WHERE plan_id = 226 ORDER BY id DESC LIMIT 1")
    mag = cur.fetchone()
    if mag:
        lbl = prepare_pallet_label_data(cur, mag['id'], linia='AGRO', source_table='magazyn')
        print("LABEL DATA FROM MAGAZYN:")
        print(lbl)
    else:
        print("No pallet in magazyn_palety_agro for plan 226")
except Exception as e:
    print(e)
