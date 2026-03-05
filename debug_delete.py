from app.db import get_db_connection
from datetime import datetime, timedelta

conn = get_db_connection()
cursor = conn.cursor()

# Sprawdzenie stanu PRZED
cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
count_04_before = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
count_05_before = cursor.fetchone()[0]

print(f"STAN PRZED DELETE:")
print(f"  Bufor 04.03: {count_04_before} rekordów")
print(f"  Bufor 05.03: {count_05_before} rekordów")

# Pokażmy co jest w buforze dla 04.03
if count_04_before > 0:
    cursor.execute("""
        SELECT id, zasyp_id, data_planu, DATE(data_planu) as data_date 
        FROM bufor 
        WHERE DATE(data_planu) = '2026-03-04'
    """)
    for row in cursor.fetchall():
        print(f"    Rekord: id={row[0]}, zasyp_id={row[1]}, data_planu={row[2]}, data_date={row[3]}")

# Wykonaj DELETE
print("\nEKSEKUWUJĘ DELETE...")
cursor.execute("""
    DELETE FROM bufor
    WHERE DATE(data_planu) = %s
""", ('2026-03-04',))

print(f"Usunięto: {cursor.rowcount} rekordów")

conn.commit()

# Sprawdzenie stanu PO
cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-04'")
count_04_after = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM bufor WHERE DATE(data_planu) = '2026-03-05'")
count_05_after = cursor.fetchone()[0]

print(f"\nSTAN PO DELETE:")
print(f"  Bufor 04.03: {count_04_after} rekordów")
print(f"  Bufor 05.03: {count_05_after} rekordów")

print(f"\nWERYFIKACJA:")
if count_04_after == 0 and count_04_before > 0:
    print("  ✓ DELETE zadziałał - bufor usunięty")
else:
    print(f"  ✗ DELETE nie zadziałał - bufor wciąż istnieje")

cursor.close()
conn.close()
