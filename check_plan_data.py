import os
from app.db import get_db_connection, get_table_name
conn = get_db_connection()
cur = conn.cursor()
table = get_table_name('plan_produkcji', 'AGRO')
cur.execute(f"SELECT id, produkt, sugerowana_folia, opakowanie_id, etykieta_id FROM {table} WHERE status='zaplanowane' AND sekcja='Workowanie'")
for row in cur.fetchall():
    print(row)
conn.close()
