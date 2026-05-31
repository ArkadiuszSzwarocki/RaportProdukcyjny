import os
from app.db import get_db_connection, get_table_name
conn = get_db_connection()
cur = conn.cursor()
table = get_table_name('plan_produkcji', 'AGRO')
cur.execute(f"DESCRIBE {table}")
for row in cur.fetchall():
    print(row[0])
conn.close()
