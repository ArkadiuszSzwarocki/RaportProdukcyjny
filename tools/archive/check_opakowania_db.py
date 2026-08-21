import mysql.connector
import sys
sys.path.append('.')
from app.db import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("SELECT id, nazwa, stan_magazynowy, lokalizacja FROM magazyn_opakowania WHERE nazwa LIKE '%Ziel%'")
rows = cursor.fetchall()
print("Milk Ziel-Żółty database entries:")
for row in rows:
    print(dict(row))
conn.close()
