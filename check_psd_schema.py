import os
from app.db import get_db_connection, get_table_name
conn = get_db_connection()
cur = conn.cursor()
table = get_table_name('plan_produkcji', 'PSD')
try:
    cur.execute(f"DESCRIBE {table}")
    for row in cur.fetchall():
        if row[0] in ('opakowanie_id', 'etykieta_id', 'sugerowana_folia'):
            print(f"FOUND IN PSD: {row[0]}")
except Exception as e:
    print(e)
conn.close()
