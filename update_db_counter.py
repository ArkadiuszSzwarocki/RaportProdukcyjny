from app.db import get_db_connection

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE plan_produkcji_agro SET start_machine_counter = 26574 WHERE status='w toku' AND start_machine_counter = 0")
    conn.commit()
    print('Rows updated:', cursor.rowcount)
except Exception as e:
    print('Error:', e)
