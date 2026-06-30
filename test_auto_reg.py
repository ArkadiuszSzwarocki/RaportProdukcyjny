from app.services.agro_warehouse_service import AgroWarehouseService
import logging
logging.basicConfig(level=logging.INFO)

print("Starting auto_register_pallet...")
# plan_id for 'Wieza 20kg 1000kg' is likely the active one. I'll pass 209 (the one from test_print2)
# actually, let's just find the active plan ID.
from app.db import get_db_connection
conn = get_db_connection()
c = conn.cursor(dictionary=True)
c.execute("SELECT id FROM plan_produkcji_agro WHERE status = 'w toku' LIMIT 1")
row = c.fetchone()
if row:
    plan_id = row['id']
    print(f"Active plan: {plan_id}")
    success = AgroWarehouseService.auto_register_pallet(plan_id, linia='AGRO', source_instance='test_script')
    print(f"Success: {success}")
else:
    print("No active plan.")
