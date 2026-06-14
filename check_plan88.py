from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, typ_zdarzenia, stan_przed, stan_po, zuzyte_worki, straty_worki, pozostalo_na_rolce FROM agro_workowanie_rozliczenie WHERE plan_id=88 ORDER BY id ASC")
    rows = cursor.fetchall()
    print(json.dumps(rows, indent=2))
