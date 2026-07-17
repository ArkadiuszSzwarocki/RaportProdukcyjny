import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT * FROM agro_workowanie_rozliczenie WHERE plan_id = 72")
rows = cursor.fetchall()
print(f"agro_workowanie_rozliczenie rows for plan 72:")
for row in rows:
    print(dict(row))
conn.close()
