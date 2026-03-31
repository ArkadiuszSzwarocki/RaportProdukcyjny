from app.db import get_db_connection
conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute('SELECT id, produkt, status, data_planu FROM bufor WHERE status="aktywny" AND data_planu < "2026-03-31"')
print(cursor.fetchall())
conn.close()
