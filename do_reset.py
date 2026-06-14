from app.core.factory import create_app
from app.db import get_db_connection

app = create_app()
with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all packaging used
    cursor.execute("SELECT * FROM agro_workowanie_rozliczenie WHERE plan_id=88")
    rozliczenia = cursor.fetchall()
    for r in rozliczenia:
        if r['typ_zdarzenia'] == 'WSADZENIE':
            opak_id = r['opakowanie_id']
            stan_przed = r['stan_przed']
            # Put it back in warehouse
            cursor.execute("UPDATE magazyn_opakowania SET stan_magazynowy = %s, lokalizacja = 'Magazyn' WHERE id = %s", (stan_przed, opak_id))
            print(f"Przywrocono opakowanie {opak_id} do Magazynu: {stan_przed} szt.")
            
    # Remove packaging links
    cursor.execute("DELETE FROM agro_plan_opakowania WHERE plan_id = 88")
    cursor.execute("DELETE FROM agro_workowanie_rozliczenie WHERE plan_id = 88")
    print("Usunieto wsadzenia i rozliczenia.")
    
    # Remove pallets
    cursor.execute("DELETE FROM palety_agro WHERE plan_id = 88")
    print("Usunieto palety.")
    
    # Reset plan metrics
    cursor.execute("UPDATE plan_produkcji_agro SET uszkodzone_worki = 0, start_machine_counter = 0, stop_machine_counter = 0, start_pallet_counter = 0 WHERE id = 88")
    print("Zresetowano metryki planu (uszkodzone_worki=0, liczniki=0).")
    
    conn.commit()
    print("=== PLAN 88 ZRESETOWANY POMYSLNIE ===")
