from app.core.factory import create_app
from app.db import get_db_connection
import json

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, opakowanie_id, is_active FROM agro_plan_opakowania WHERE plan_id=88")
    print("WSADZENIA (aktywne rolki):", json.dumps(cursor.fetchall(), indent=2))
    
    cursor.execute("SELECT id, typ_zdarzenia, stan_przed, zuzyte_worki, pozostalo_na_rolce FROM agro_workowanie_rozliczenie WHERE plan_id=88")
    print("ROZLICZENIA:", json.dumps(cursor.fetchall(), indent=2))
    
    cursor.execute("SELECT id, nr_palety FROM palety_agro WHERE plan_id=88")
    print("PALETY:", json.dumps(cursor.fetchall(), indent=2))
    
    cursor.execute("SELECT uszkodzone_worki, start_machine_counter, stop_machine_counter, zrobione_palety FROM plan_produkcji_agro WHERE id=88")
    print("PLAN:", json.dumps(cursor.fetchall(), indent=2))
