from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, typ_zdarzenia, opakowanie_id, stan_przed, stan_po, pozostalo_na_rolce FROM agro_workowanie_rozliczenie WHERE plan_id=88")
    rows = cursor.fetchall()
    print("ROZLICZENIA:")
    print(json.dumps(rows, indent=2))
    
    cursor.execute("SELECT id, opakowanie_id, is_active FROM agro_plan_opakowania WHERE plan_id=88")
    rows = cursor.fetchall()
    print("WSADZENIA:")
    print(json.dumps(rows, indent=2))
    
    cursor.execute("SELECT id, potwierdzona FROM agro_palety_rejestr WHERE plan_id=88")
    rows = cursor.fetchall()
    print("PALETY:")
    print(json.dumps(rows, indent=2))
