from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id, status FROM wnioski_wolne WHERE id IN (20,21,22,23,24)")
results = cursor.fetchall()
for id_, status in results:
    print(f'ID {id_}: {status}')
conn.close()
