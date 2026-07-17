import os
import sys

sys.path.insert(0, os.getcwd())
from app.core.database import get_db_connection
from app.utils.pallet_label import prepare_pallet_label_data

try:
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM palety_workowanie_agro ORDER BY id DESC LIMIT 1")
    pw = cur.fetchone()
    if pw:
        lbl = prepare_pallet_label_data(cur, pw['id'], linia='AGRO', source_table='workowanie')
        print("LABEL DATA FROM WORKOWANIE:")
        print(lbl)
    else:
        print("No pallet in palety_workowanie_agro")
        
except Exception as e:
    print(e)
