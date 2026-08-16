import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check produkty_receptury for plan 222 product
print("--- plan 222 product ---")
cursor.execute("SELECT produkt, nr_receptury FROM plan_produkcji_agro WHERE id=222")
row = cursor.fetchone()
print(row)

if row:
    produkt = row['produkt']
    nr_receptury = row.get('nr_receptury', '')
    print(f"\nSearching receptury for: '{produkt}'")
    cursor.execute("SELECT * FROM produkty_receptury WHERE nazwa_produktu = %s", (produkt,))
    for r in cursor.fetchall():
        print(r)

# Check plan_agro table
print("\n--- DESCRIBE plan_agro ---")
cursor.execute("DESCRIBE plan_agro")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- sample from plan_agro ---")
cursor.execute("SELECT * FROM plan_agro LIMIT 3")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
