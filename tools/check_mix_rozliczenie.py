import sys
sys.path.append('a:\\GitHub\\RaportProdukcyjny')
from app.core.database import get_db_connection

conn = get_db_connection()
cursor = conn.cursor(dictionary=True)
cursor.execute("USE biblioteka")

# Check if there is any table with recipe ingredients (składniki receptury)
# Look at agro_mix_rozliczenie
print("--- DESCRIBE agro_mix_rozliczenie ---")
cursor.execute("DESCRIBE agro_mix_rozliczenie")
for r in cursor.fetchall():
    print(r['Field'], r['Type'])

print("\n--- sample agro_mix_rozliczenie for plan 222 ---")
cursor.execute("SELECT * FROM agro_mix_rozliczenie WHERE plan_id = 222 LIMIT 10")
for r in cursor.fetchall():
    print(r)

cursor.close()
conn.close()
