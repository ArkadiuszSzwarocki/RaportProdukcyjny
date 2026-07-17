import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

print("--- Recipe details ---")
cursor.execute("SELECT * FROM produkty_receptury WHERE nazwa_produktu = 'MLECZNA PYCHA CZERWONA'")
recipes = cursor.fetchall()
for r in recipes:
    print(r)
    # Check if there are other tables related to recipe ingredients
    cursor.execute("SHOW TABLES LIKE '%receptura%'")
    print(cursor.fetchall())

cursor.close()
conn.close()
