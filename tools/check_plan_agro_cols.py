import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# What columns does plan_produkcji_agro SELECT return as a tuple in dashboards?
cursor.execute("SELECT * FROM plan_produkcji_agro WHERE id = 222")
row = cursor.fetchone()
print("plan_produkcji_agro row:")
for k, v in row.items():
    print(f"  {k}: {v}")

cursor.close()
conn.close()
