import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT * FROM plan_produkcji_agro WHERE id = 72")
plan = cursor.fetchone()
print("Plan 72 details:")
for k, v in plan.items():
    print(f"  {k}: {v} (type: {type(v)})")
conn.close()
