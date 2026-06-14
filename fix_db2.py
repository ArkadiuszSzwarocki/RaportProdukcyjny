from app import app
from app.db import get_db_connection
import json

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, stan_przed, stan_po, zuzyte_worki FROM agro_workowanie_rozliczenie WHERE typ_zdarzenia='ZAMKNIECIE' AND zuzyte_worki != (stan_przed - stan_po)")
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            cursor.execute("UPDATE agro_workowanie_rozliczenie SET zuzyte_worki = %s WHERE id = %s", (row['stan_przed'] - row['stan_po'], row['id']))
        conn.commit()
    print(json.dumps(rows))
