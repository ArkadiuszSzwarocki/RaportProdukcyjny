import sys
sys.path.insert(0, 'c:/Users/arkad/Documents/GitHub/RaportProdukcyjny')
from app.db import get_db_connection
from datetime import date

conn = get_db_connection()
cursor = conn.cursor()

# Check if test plan exists
cursor.execute("SELECT id, produkt, sekcja, status, is_deleted, data_planu FROM plan_produkcji WHERE id=472")
row = cursor.fetchone()
if row:
    print(f"[OK] Plan 472 found in DB:")
    print(f"     ID: {row[0]}")
    print(f"     Produkt: {row[1]}")
    print(f"     Sekcja: {row[2]}")
    print(f"     Status: {row[3]}")
    print(f"     is_deleted: {row[4]}")
    print(f"     data_planu: {row[5]}")
else:
    print("[!] Plan 472 not found in DB")

# Check what plans exist for today
print(f"\n[*] All plans for {date.today()}:")
cursor.execute("""
SELECT id, produkt, sekcja, status, is_deleted 
FROM plan_produkcji 
WHERE DATE(data_planu) = %s
ORDER BY id DESC
""", (date.today(),))
rows = cursor.fetchall()
for r in rows:
    print(f"  ID={r[0]}, Produkt={r[1]}, Sekcja={r[2]}, Status={r[3]}, is_deleted={r[4]}")

if not rows:
    print("  (none)")

conn.close()
