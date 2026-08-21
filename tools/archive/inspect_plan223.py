import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- Plan 223 ---")
cursor.execute("SELECT * FROM plan_produkcji_agro WHERE id = 223")
plan = cursor.fetchone()
import json
print(json.dumps(plan, indent=2, default=str))

print("--- Columns in plan_produkcji_agro ---")
cursor.execute("SHOW COLUMNS FROM plan_produkcji_agro")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

cursor.close()
conn.close()
