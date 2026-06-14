from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, typ_zdarzenia, stan_przed, stan_po, zuzyte_worki, straty_worki, pozostalo_na_rolce FROM agro_workowanie_rozliczenie WHERE typ_zdarzenia='ZAMKNIECIE' ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    
    # Fix incorrect rows
    for row in rows:
        expected = row['stan_przed'] - row['stan_po']
        if row['zuzyte_worki'] != expected:
            cursor.execute("UPDATE agro_workowanie_rozliczenie SET zuzyte_worki = %s WHERE id = %s", (expected, row['id']))
            conn.commit()
            print(f"Fixed row {row['id']}: set zuzyte_worki to {expected}")
            
    print(json.dumps(rows, indent=2))
