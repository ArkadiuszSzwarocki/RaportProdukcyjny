from app.db import get_db_connection
from app.services.mqtt_service import get_latest_data
import time

try:
    c = get_latest_data().get('counter', 0)
    print('Current counter:', c)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji_agro SET start_machine_counter = %s WHERE status='w toku' AND start_machine_counter = 0", (c,))
    conn.commit()
    print('Rows updated:', cursor.rowcount)
except Exception as e:
    print('Error:', e)
